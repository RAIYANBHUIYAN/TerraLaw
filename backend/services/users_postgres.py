import uuid
from datetime import datetime

from backend.db import get_connection


def now_iso() -> str:
    return datetime.now().isoformat()


def register_user(user_id: str, password_hash: str) -> dict:
    clean_id = user_id.strip()
    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM users WHERE id = %s", (clean_id,)).fetchone()
        if existing:
            raise ValueError("User ID already exists.")
        conn.execute(
            "INSERT INTO users (id, password_hash) VALUES (%s, %s)",
            (clean_id, password_hash),
        )
        conn.commit()
    return {"user_id": clean_id}


def authenticate_user(user_id: str, password_hash: str) -> dict | None:
    clean_id = user_id.strip()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE id = %s AND password_hash = %s",
            (clean_id, password_hash),
        ).fetchone()
    if not row:
        return None
    return {"user_id": clean_id}


def _conversation_row_to_dict(row: dict, messages: list[dict]) -> dict:
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
        "messages": messages,
    }


def _fetch_messages(conn, conversation_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT sender, text, created_at
        FROM messages
        WHERE conversation_id = %s
        ORDER BY created_at ASC
        """,
        (conversation_id,),
    ).fetchall()
    return [
        {
            "sender": row["sender"],
            "text": row["text"],
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]


def list_conversations(user_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM conversations
            WHERE user_id = %s
            ORDER BY updated_at DESC
            """,
            (user_id,),
        ).fetchall()
        return [
            _conversation_row_to_dict(row, _fetch_messages(conn, str(row["id"])))
            for row in rows
        ]


def get_conversation(user_id: str, conversation_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM conversations
            WHERE user_id = %s AND id = %s
            """,
            (user_id, conversation_id),
        ).fetchone()
        if not row:
            return None
        return _conversation_row_to_dict(row, _fetch_messages(conn, conversation_id))


def create_conversation(user_id: str, title: str = "New chat") -> dict:
    conversation_id = str(uuid.uuid4())
    with get_connection() as conn:
        user = conn.execute("SELECT id FROM users WHERE id = %s", (user_id,)).fetchone()
        if not user:
            raise ValueError("User not found.")
        row = conn.execute(
            """
            INSERT INTO conversations (id, user_id, title)
            VALUES (%s, %s, %s)
            RETURNING id, title, created_at, updated_at
            """,
            (conversation_id, user_id, title),
        ).fetchone()
        conn.commit()
    return _conversation_row_to_dict(row, [])


def append_message(user_id: str, conversation_id: str, sender: str, text: str) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM conversations
            WHERE user_id = %s AND id = %s
            """,
            (user_id, conversation_id),
        ).fetchone()
        if not row:
            raise ValueError("Conversation not found.")

        message_count = conn.execute(
            "SELECT COUNT(*) AS count FROM messages WHERE conversation_id = %s",
            (conversation_id,),
        ).fetchone()["count"]

        title = row["title"]
        if message_count == 0 and sender == "user":
            trimmed = " ".join(text.strip().split())
            title = trimmed[:40] + ("..." if len(trimmed) > 40 else "") if trimmed else "New chat"

        conn.execute(
            """
            INSERT INTO messages (id, conversation_id, sender, text)
            VALUES (%s, %s, %s, %s)
            """,
            (str(uuid.uuid4()), conversation_id, sender, text),
        )
        conn.execute(
            """
            UPDATE conversations
            SET title = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (title, conversation_id),
        )
        conn.commit()

        updated = conn.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM conversations
            WHERE id = %s
            """,
            (conversation_id,),
        ).fetchone()
        messages = _fetch_messages(conn, conversation_id)

    return _conversation_row_to_dict(updated, messages)
