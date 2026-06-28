import hashlib
import json
import uuid
from datetime import datetime

from backend.db import is_postgres_configured
from model.paths import APP_DATA_DIR

USERS_STORE = APP_DATA_DIR / "users.json"
CHAT_STORE = APP_DATA_DIR / "chat_history.json"


def now_iso() -> str:
    return datetime.now().isoformat()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _using_postgres() -> bool:
    return is_postgres_configured()


def load_users() -> dict:
    if not USERS_STORE.exists():
        return {}
    try:
        return json.loads(USERS_STORE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_users(users: dict):
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    USERS_STORE.write_text(json.dumps(users, indent=2), encoding="utf-8")


def load_chat_store() -> dict:
    if not CHAT_STORE.exists():
        return {"users": {}}
    try:
        payload = json.loads(CHAT_STORE.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return {"users": {"legacy": payload}}
        if "users" not in payload:
            payload["users"] = {}
        return payload
    except Exception:
        return {"users": {}}


def save_chat_store(store: dict):
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    CHAT_STORE.write_text(json.dumps(store, indent=2), encoding="utf-8")


def _register_user_json(user_id: str, password: str) -> dict:
    clean_id = user_id.strip()
    if not clean_id or not password:
        raise ValueError("User ID and password are required.")
    users = load_users()
    if clean_id in users:
        raise ValueError("User ID already exists.")
    users[clean_id] = {"password_hash": hash_password(password), "created_at": now_iso()}
    save_users(users)
    return {"user_id": clean_id}


def _authenticate_user_json(user_id: str, password: str) -> dict:
    clean_id = user_id.strip()
    users = load_users()
    user = users.get(clean_id)
    if not user or user.get("password_hash") != hash_password(password):
        raise ValueError("Invalid user ID or password.")
    return {"user_id": clean_id}


def _list_conversations_json(user_id: str) -> list[dict]:
    store = load_chat_store()
    conversations = store["users"].get(user_id, [])
    return sorted(conversations, key=lambda item: item.get("updated_at", ""), reverse=True)


def _get_conversation_json(user_id: str, conversation_id: str) -> dict | None:
    for conversation in _list_conversations_json(user_id):
        if conversation["id"] == conversation_id:
            return conversation
    return None


def _create_conversation_json(user_id: str, title: str = "New chat") -> dict:
    conversation = {
        "id": str(uuid.uuid4()),
        "title": title,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "messages": [],
    }
    store = load_chat_store()
    store["users"].setdefault(user_id, [])
    store["users"][user_id].insert(0, conversation)
    save_chat_store(store)
    return conversation


def _append_message_json(user_id: str, conversation_id: str, sender: str, text: str) -> dict:
    store = load_chat_store()
    conversations = store["users"].get(user_id, [])
    for conversation in conversations:
        if conversation["id"] != conversation_id:
            continue
        if not conversation["messages"] and sender == "user":
            trimmed = " ".join(text.strip().split())
            conversation["title"] = trimmed[:40] + ("..." if len(trimmed) > 40 else "") if trimmed else "New chat"
        conversation["messages"].append(
            {"sender": sender, "text": text, "created_at": now_iso()}
        )
        conversation["updated_at"] = now_iso()
        save_chat_store(store)
        return conversation
    raise ValueError("Conversation not found.")


def register_user(user_id: str, password: str) -> dict:
    clean_id = user_id.strip()
    if not clean_id or not password:
        raise ValueError("User ID and password are required.")

    if _using_postgres():
        from backend.services import users_postgres

        return users_postgres.register_user(clean_id, hash_password(password))
    return _register_user_json(clean_id, password)


def authenticate_user(user_id: str, password: str) -> dict:
    clean_id = user_id.strip()
    if _using_postgres():
        from backend.services import users_postgres

        result = users_postgres.authenticate_user(clean_id, hash_password(password))
        if not result:
            raise ValueError("Invalid user ID or password.")
        return result
    return _authenticate_user_json(clean_id, password)


def list_conversations(user_id: str) -> list[dict]:
    if _using_postgres():
        from backend.services import users_postgres

        return users_postgres.list_conversations(user_id)
    return _list_conversations_json(user_id)


def get_conversation(user_id: str, conversation_id: str) -> dict | None:
    if _using_postgres():
        from backend.services import users_postgres

        return users_postgres.get_conversation(user_id, conversation_id)
    return _get_conversation_json(user_id, conversation_id)


def create_conversation(user_id: str, title: str = "New chat") -> dict:
    if _using_postgres():
        from backend.services import users_postgres

        return users_postgres.create_conversation(user_id, title)
    return _create_conversation_json(user_id, title)


def append_message(user_id: str, conversation_id: str, sender: str, text: str) -> dict:
    if _using_postgres():
        from backend.services import users_postgres

        return users_postgres.append_message(user_id, conversation_id, sender, text)
    return _append_message_json(user_id, conversation_id, sender, text)
