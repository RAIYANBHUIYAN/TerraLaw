"""Test PostgreSQL connectivity for TerraLaw BD."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from backend.db import get_connection, init_schema, is_postgres_configured  # noqa: E402
from backend.services.users import (  # noqa: E402
    authenticate_user,
    create_conversation,
    register_user,
)


def main():
    print("=== TerraLaw PostgreSQL Test ===\n")

    if not is_postgres_configured():
        print("FAIL: DATABASE_URL is not set in .env")
        sys.exit(1)

    print("1. Connecting and ensuring schema...")
    try:
        init_schema()
        with get_connection() as conn:
            users = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
            conversations = conn.execute("SELECT COUNT(*) AS count FROM conversations").fetchone()["count"]
        print(f"   OK - users: {users}, conversations: {conversations}")
    except Exception as exc:
        print(f"   FAIL: {exc}")
        sys.exit(1)

    test_user = "__pinecone_test_user__"
    print("\n2. Register + login test...")
    try:
        try:
            register_user(test_user, "testpass123")
        except ValueError as exc:
            if "already exists" not in str(exc):
                raise
        auth = authenticate_user(test_user, "testpass123")
        print(f"   OK - authenticated {auth['user_id']}")
    except Exception as exc:
        print(f"   FAIL: {exc}")
        sys.exit(1)

    print("\n3. Conversation test...")
    try:
        conversation = create_conversation(test_user, "Postgres test chat")
        print(f"   OK - created conversation {conversation['id']}")
    except Exception as exc:
        print(f"   FAIL: {exc}")
        sys.exit(1)

    print("\n=== PostgreSQL is working ===")


if __name__ == "__main__":
    main()
