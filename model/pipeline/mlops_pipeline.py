import argparse
import json
import platform
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests

from model.pipeline.evaluate_rag import evaluate_cases
from model.paths import (
    BENCHMARKS_DIR,
    DEFAULT_API_BASE_URL,
    MLOPS_RUNS_DIR,
    PROJECT_ROOT,
)
from model.pipeline.rag_pipeline import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_PROCESSED_DATA_DIR,
    DEFAULT_VECTOR_DIR,
    build_vectorstore,
)

DEFAULT_TRACKING_DIR = MLOPS_RUNS_DIR
DEFAULT_CASES_PATH = BENCHMARKS_DIR / "eval_cases.json"


def _run_git_command(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return result.stdout.strip() or None


def _git_context() -> dict:
    return {
        "branch": _run_git_command("rev-parse", "--abbrev-ref", "HEAD"),
        "commit": _run_git_command("rev-parse", "HEAD"),
        "short_commit": _run_git_command("rev-parse", "--short", "HEAD"),
        "is_dirty": bool(_run_git_command("status", "--short")),
    }


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _health_url(api_base_url: str) -> str:
    return f"{api_base_url.rstrip('/')}/"


def _ask_url(api_base_url: str) -> str:
    return f"{api_base_url.rstrip('/')}/ask"


def _parse_api_base_url(api_base_url: str) -> tuple[str, str, int]:
    parts = urlsplit(api_base_url)
    scheme = parts.scheme or "http"
    host = parts.hostname or "127.0.0.1"
    port = parts.port or 8000
    return scheme, host, port


def _replace_port(api_base_url: str, port: int) -> str:
    parts = urlsplit(api_base_url)
    scheme = parts.scheme or "http"
    host = parts.hostname or "127.0.0.1"
    netloc = f"{host}:{port}"
    return urlunsplit((scheme, netloc, parts.path, parts.query, parts.fragment)).rstrip("/")


def _find_free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        sock.listen(1)
        return sock.getsockname()[1]


def api_is_healthy(api_base_url: str, timeout_seconds: int = 5) -> bool:
    try:
        response = requests.get(_health_url(api_base_url), timeout=timeout_seconds)
        return response.ok
    except Exception:
        return False


def wait_for_api(api_base_url: str, timeout_seconds: int = 90) -> bool:
    started_at = time.time()
    while time.time() - started_at < timeout_seconds:
        if api_is_healthy(api_base_url):
            return True
        time.sleep(2)
    return False


def start_api_server(api_base_url: str, run_dir: Path):
    _, host, port = _parse_api_base_url(api_base_url)
    stdout_path = run_dir / "backend.out.log"
    stderr_path = run_dir / "backend.err.log"

    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app:app",
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=PROJECT_ROOT,
        stdout=stdout_handle,
        stderr=stderr_handle,
    )
    return process, stdout_path, stderr_path, stdout_handle, stderr_handle


def stop_api_server(process: subprocess.Popen | None):
    if process is None or process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run_pipeline(
    processed_data_dir: Path = DEFAULT_PROCESSED_DATA_DIR,
    vector_dir: Path = DEFAULT_VECTOR_DIR,
    embedding_model_name: str = DEFAULT_EMBEDDING_MODEL,
    api_base_url: str = DEFAULT_API_BASE_URL,
    cases_path: Path = DEFAULT_CASES_PATH,
    tracking_dir: Path = DEFAULT_TRACKING_DIR,
    skip_build: bool = False,
    skip_eval: bool = False,
    keep_api_running: bool = False,
):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = tracking_dir / f"run_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    latest_path = tracking_dir / "latest_run.json"

    pipeline_run = {
        "run_id": run_dir.name,
        "started_at": datetime.now().isoformat(),
        "status": "running",
        "project_root": str(PROJECT_ROOT),
        "python_version": sys.version,
        "platform": platform.platform(),
        "git": _git_context(),
        "config": {
            "processed_data_dir": str(processed_data_dir),
            "vector_dir": str(vector_dir),
            "embedding_model_name": embedding_model_name,
            "api_base_url": api_base_url,
            "cases_path": str(cases_path),
            "skip_build": skip_build,
            "skip_eval": skip_eval,
            "keep_api_running": keep_api_running,
        },
    }
    _write_json(run_dir / "pipeline_run.json", pipeline_run)

    api_process = None
    stdout_handle = None
    stderr_handle = None

    try:
        if not skip_build:
            pipeline_run["build"] = build_vectorstore(
                processed_data_dir=processed_data_dir,
                vector_dir=vector_dir,
                embedding_model_name=embedding_model_name,
            )
            _write_json(run_dir / "pipeline_run.json", pipeline_run)

        if not skip_eval:
            evaluation_api_base_url = api_base_url

            if not skip_build:
                _, host, _ = _parse_api_base_url(api_base_url)
                evaluation_api_base_url = _replace_port(
                    api_base_url,
                    _find_free_port(host),
                )
                api_process, stdout_path, stderr_path, stdout_handle, stderr_handle = start_api_server(
                    api_base_url=evaluation_api_base_url,
                    run_dir=run_dir,
                )
                if not wait_for_api(evaluation_api_base_url):
                    raise RuntimeError(
                        "Fresh API server did not become healthy within the expected time window."
                    )
                pipeline_run["api"] = {
                    "mode": "started_fresh_for_build",
                    "health_url": _health_url(evaluation_api_base_url),
                    "pid": api_process.pid,
                    "stdout_log": str(stdout_path),
                    "stderr_log": str(stderr_path),
                }
            elif api_is_healthy(api_base_url):
                pipeline_run["api"] = {
                    "mode": "reused_existing",
                    "health_url": _health_url(api_base_url),
                }
            else:
                api_process, stdout_path, stderr_path, stdout_handle, stderr_handle = start_api_server(
                    api_base_url=api_base_url,
                    run_dir=run_dir,
                )
                if not wait_for_api(api_base_url):
                    raise RuntimeError(
                        "API server did not become healthy within the expected time window."
                    )
                pipeline_run["api"] = {
                    "mode": "started_by_pipeline",
                    "health_url": _health_url(api_base_url),
                    "pid": api_process.pid,
                    "stdout_log": str(stdout_path),
                    "stderr_log": str(stderr_path),
                }

            evaluation_report_path = run_dir / "evaluation_report.json"
            pipeline_run["evaluation"] = evaluate_cases(
                api_url=_ask_url(evaluation_api_base_url),
                cases_path=cases_path,
                reports_dir=run_dir,
                save_report=True,
                report_path=evaluation_report_path,
            )
            _write_json(run_dir / "pipeline_run.json", pipeline_run)

        pipeline_run["status"] = "completed"
        pipeline_run["finished_at"] = datetime.now().isoformat()
        _write_json(run_dir / "pipeline_run.json", pipeline_run)
        _write_json(latest_path, pipeline_run)
        return pipeline_run
    except Exception as exc:
        pipeline_run["status"] = "failed"
        pipeline_run["finished_at"] = datetime.now().isoformat()
        pipeline_run["error"] = str(exc)
        _write_json(run_dir / "pipeline_run.json", pipeline_run)
        _write_json(latest_path, pipeline_run)
        raise
    finally:
        if api_process and not keep_api_running:
            stop_api_server(api_process)
        if stdout_handle:
            stdout_handle.close()
        if stderr_handle:
            stderr_handle.close()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the TerraLaw BD local MLOps pipeline."
    )
    parser.add_argument(
        "--processed-data-dir",
        default=str(DEFAULT_PROCESSED_DATA_DIR),
        help="Directory containing cleaned legal text files.",
    )
    parser.add_argument(
        "--vector-dir",
        default=str(DEFAULT_VECTOR_DIR),
        help="Directory where vector artifacts are stored.",
    )
    parser.add_argument(
        "--embedding-model-name",
        default=DEFAULT_EMBEDDING_MODEL,
        help="Embedding model used for vectorstore creation.",
    )
    parser.add_argument(
        "--api-base-url",
        default=DEFAULT_API_BASE_URL,
        help="Base URL for the local API health and evaluation calls.",
    )
    parser.add_argument(
        "--cases",
        default=str(DEFAULT_CASES_PATH),
        help="Benchmark cases file used during evaluation.",
    )
    parser.add_argument(
        "--tracking-dir",
        default=str(DEFAULT_TRACKING_DIR),
        help="Directory where pipeline run metadata and artifacts are written.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip vectorstore rebuild and reuse existing artifacts.",
    )
    parser.add_argument(
        "--skip-eval",
        action="store_true",
        help="Skip API evaluation after build.",
    )
    parser.add_argument(
        "--keep-api-running",
        action="store_true",
        help="Keep the API alive if the pipeline had to start it.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result = run_pipeline(
        processed_data_dir=Path(args.processed_data_dir),
        vector_dir=Path(args.vector_dir),
        embedding_model_name=args.embedding_model_name,
        api_base_url=args.api_base_url,
        cases_path=Path(args.cases),
        tracking_dir=Path(args.tracking_dir),
        skip_build=args.skip_build,
        skip_eval=args.skip_eval,
        keep_api_running=args.keep_api_running,
    )
    print(json.dumps(result, indent=2))
