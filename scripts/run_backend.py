"""Run the FastAPI backend."""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main():
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]
    # --reload can hang on Windows when ML models load slowly at import time.
    if "--reload" in sys.argv:
        cmd.append("--reload")

    subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)


if __name__ == "__main__":
    main()
