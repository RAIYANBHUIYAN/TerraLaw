"""Initialize PostgreSQL schema for TerraLaw BD."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from backend.db import init_schema, is_postgres_configured  # noqa: E402


def main():
    if not is_postgres_configured():
        print("Error: DATABASE_URL is not set in .env")
        print("Example (Neon):")
        print("  DATABASE_URL=postgresql://user:pass@ep-xxx.region.aws.neon.tech/neondb?sslmode=require")
        sys.exit(1)

    init_schema()
    print("PostgreSQL schema created successfully.")
    print("Tables: users, conversations, messages")


if __name__ == "__main__":
    main()
