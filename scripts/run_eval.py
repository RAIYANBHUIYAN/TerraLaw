"""Run RAG benchmark evaluation against the live API."""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main():
    subprocess.run(
        [sys.executable, "-m", "model.pipeline.evaluate_rag", *sys.argv[1:]],
        cwd=PROJECT_ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
