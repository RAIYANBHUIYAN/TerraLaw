"""Build the vector index from processed legal data."""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main():
    subprocess.run(
        [sys.executable, "-m", "model.pipeline.rag_pipeline"],
        cwd=PROJECT_ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
