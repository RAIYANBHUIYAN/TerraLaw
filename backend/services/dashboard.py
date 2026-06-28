import json
import re
from collections import Counter
from datetime import datetime, timedelta

from model.paths import BACKEND_REPORTS_DIR, MODEL_REPORTS_DIR

from backend.config import GROQ_MODEL
from backend.state import runtime_metrics

RUNTIME_DASHBOARD_FILE = BACKEND_REPORTS_DIR / "runtime_dashboard.json"


def default_dashboard_store():
    return {
        "request_log": [],
        "login_events": [],
        "token_totals": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
        "model_usage": {},
        "mode_usage": {},
        "dispute_usage": {},
        "latency_ms": [],
        "updated_at": None,
    }


def load_dashboard_store():
    if not RUNTIME_DASHBOARD_FILE.exists():
        return default_dashboard_store()

    try:
        payload = json.loads(RUNTIME_DASHBOARD_FILE.read_text(encoding="utf-8"))
    except Exception:
        return default_dashboard_store()

    base = default_dashboard_store()
    base.update(payload)
    migrated_requests = []
    for event in payload.get("request_log", []):
        migrated = dict(event)
        migrated.pop("question_preview", None)
        migrated["dispute_label"] = migrated.get("dispute_label") or "Legacy request"
        migrated_requests.append(migrated)
    base["request_log"] = migrated_requests
    base["login_events"] = payload.get("login_events", [])
    base["token_totals"].update(payload.get("token_totals", {}))
    base["model_usage"] = payload.get("model_usage", {})
    base["mode_usage"] = payload.get("mode_usage", {})
    base["dispute_usage"] = payload.get("dispute_usage", {})
    base["latency_ms"] = payload.get("latency_ms", [])
    return base


dashboard_store = load_dashboard_store()


def save_dashboard_store():
    BACKEND_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DASHBOARD_FILE.write_text(
        json.dumps(dashboard_store, indent=2),
        encoding="utf-8",
    )


def coerce_int(value) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def estimate_tokens(text: str) -> int:
    compact = (text or "").strip()
    if not compact:
        return 0
    return max(1, len(compact) // 4)


def extract_usage(response, prompt_text: str, answer_text: str):
    usage = getattr(response, "usage", None)
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0

    if usage:
        prompt_tokens = coerce_int(
            getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", None)
        )
        completion_tokens = coerce_int(
            getattr(usage, "output_tokens", None) or getattr(usage, "completion_tokens", None)
        )
        total_tokens = coerce_int(getattr(usage, "total_tokens", None))

    if not prompt_tokens:
        prompt_tokens = estimate_tokens(prompt_text)
    if not completion_tokens:
        completion_tokens = estimate_tokens(answer_text)
    if not total_tokens:
        total_tokens = prompt_tokens + completion_tokens

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def record_request_event(dispute_label: str, mode: str, latency_ms: float, token_usage: dict, status_label: str):
    event = {
        "timestamp": datetime.now().isoformat(),
        "dispute_label": dispute_label,
        "mode": mode,
        "latency_ms": round(latency_ms, 2),
        "prompt_tokens": token_usage["prompt_tokens"],
        "completion_tokens": token_usage["completion_tokens"],
        "total_tokens": token_usage["total_tokens"],
        "status": status_label,
        "model": GROQ_MODEL if token_usage["total_tokens"] else "vectorstore-only",
    }

    dashboard_store["request_log"].append(event)
    dashboard_store["request_log"] = dashboard_store["request_log"][-200:]

    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        dashboard_store["token_totals"][key] = (
            coerce_int(dashboard_store["token_totals"].get(key)) + token_usage[key]
        )

    dashboard_store["latency_ms"].append(round(latency_ms, 2))
    dashboard_store["latency_ms"] = dashboard_store["latency_ms"][-200:]

    model_usage = Counter(dashboard_store.get("model_usage", {}))
    model_usage[event["model"]] += 1
    dashboard_store["model_usage"] = dict(model_usage)

    mode_usage = Counter(dashboard_store.get("mode_usage", {}))
    mode_usage[mode] += 1
    dashboard_store["mode_usage"] = dict(mode_usage)

    dispute_usage = Counter(dashboard_store.get("dispute_usage", {}))
    dispute_usage[dispute_label] += 1
    dashboard_store["dispute_usage"] = dict(dispute_usage)
    dashboard_store["updated_at"] = event["timestamp"]
    save_dashboard_store()


def record_login_event(user_id: str, role: str):
    event = {
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id,
        "role": role,
    }
    dashboard_store["login_events"].append(event)
    dashboard_store["login_events"] = dashboard_store["login_events"][-200:]
    runtime_metrics["logins"] += 1
    if role == "admin":
        runtime_metrics["admin_logins"] += 1
    else:
        runtime_metrics["user_logins"] += 1
    dashboard_store["updated_at"] = event["timestamp"]
    save_dashboard_store()


def latest_benchmark_report():
    reports = sorted(
        MODEL_REPORTS_DIR.glob("metrics_report_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        return None

    try:
        payload = json.loads(reports[0].read_text(encoding="utf-8"))
    except Exception:
        return None

    return {
        "path": str(reports[0]),
        "generated_at": payload.get("generated_at"),
        "summary": payload.get("summary", {}),
    }


def hourly_request_series():
    now = datetime.now()
    series = []
    events = dashboard_store.get("request_log", [])
    for offset in range(23, -1, -1):
        start = now - timedelta(hours=offset)
        bucket_label = start.strftime("%H:%M")
        bucket_key = start.strftime("%Y-%m-%d %H")
        count = 0
        for event in events:
            stamp = event.get("timestamp")
            if not stamp:
                continue
            try:
                event_dt = datetime.fromisoformat(stamp)
            except ValueError:
                continue
            if event_dt.strftime("%Y-%m-%d %H") == bucket_key:
                count += 1
        series.append({"label": bucket_label, "value": count})
    return series


def token_series():
    events = dashboard_store.get("request_log", [])[-20:]
    series = []
    for index, event in enumerate(events, start=1):
        series.append(
            {
                "label": str(index),
                "value": coerce_int(event.get("total_tokens")),
            }
        )
    return series


def dashboard_payload(vectorstore_loaded: bool):
    latest_report = latest_benchmark_report()
    latency_values = [
        coerce_int(value) for value in dashboard_store.get("latency_ms", []) if value is not None
    ]
    recent_requests = dashboard_store.get("request_log", [])[-10:]
    recent_logins = dashboard_store.get("login_events", [])[-10:]
    top_acts = sorted(
        (
            {"label": key.replace("act:", ""), "value": value}
            for key, value in runtime_metrics.items()
            if key.startswith("act:")
        ),
        key=lambda item: item["value"],
        reverse=True,
    )[:5]
    benchmark_metrics = []
    if latest_report and latest_report.get("summary"):
        benchmark_metrics = [
            {"label": key.replace("_", " "), "value": value}
            for key, value in latest_report["summary"].items()
            if key != "cases"
        ]
    dispute_analytics = sorted(
        (
            {"label": label, "value": value}
            for label, value in dashboard_store.get("dispute_usage", {}).items()
        ),
        key=lambda item: item["value"],
        reverse=True,
    )

    return {
        "overview": {
            "queries": runtime_metrics.get("queries", 0),
            "logins": runtime_metrics.get("logins", 0),
            "rag_answers": runtime_metrics.get("rag_answers", 0),
            "fallback_answers": runtime_metrics.get("llm_fallback_answers", 0)
            + runtime_metrics.get("vector_only_fallback_answers", 0),
            "errors": runtime_metrics.get("llm_errors", 0),
            "avg_latency_ms": round(sum(latency_values) / len(latency_values), 2) if latency_values else 0.0,
            "vectorstore_loaded": vectorstore_loaded,
        },
        "token_totals": dashboard_store.get("token_totals", {}),
        "runtime_metrics": dict(runtime_metrics),
        "mode_usage": dashboard_store.get("mode_usage", {}),
        "model_usage": dashboard_store.get("model_usage", {}),
        "dispute_usage": dashboard_store.get("dispute_usage", {}),
        "dispute_analytics": dispute_analytics,
        "top_acts": top_acts,
        "traffic_series": hourly_request_series(),
        "token_series": token_series(),
        "recent_requests": recent_requests,
        "recent_logins": recent_logins,
        "latest_benchmark": latest_report,
        "benchmark_metrics": benchmark_metrics,
        "updated_at": dashboard_store.get("updated_at"),
    }


def sanitize_user_id(user_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.@-]+", "", user_id)[:64] or "unknown"
