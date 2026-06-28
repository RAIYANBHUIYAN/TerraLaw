"""Launch the TerraLaw Next.js frontend."""

import subprocess
import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def main():
    subprocess.run(
        ["npm", "run", "dev"],
        cwd=FRONTEND_DIR,
        check=True,
        shell=True,
    )


if __name__ == "__main__":
    main()