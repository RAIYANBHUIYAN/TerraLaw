import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

from model.core.terralaw_core import ACT_CATALOG
from backend.config import ADMIN_PASSWORD, ADMIN_USERNAME, CORS_ORIGINS
from backend.db import init_schema, is_postgres_configured
from backend.services.dashboard import (
    dashboard_payload,
    record_login_event,
    sanitize_user_id,
)
from backend.services.rag import answer_question
from backend.services.users import (
    append_message,
    authenticate_user,
    create_conversation,
    get_conversation,
    list_conversations,
    register_user,
)
from backend.services.vectorstore import get_vectorstore
from backend.state import runtime_metrics

app = FastAPI(title="TerraLaw BD API")
security = HTTPBasic()
DASHBOARD_TEMPLATE = Path(__file__).resolve().parent / "templates" / "dashboard.html"


@app.on_event("startup")
def startup_db():
    if is_postgres_configured():
        try:
            init_schema()
            print("PostgreSQL schema ready.")
        except Exception as exc:
            print(f"PostgreSQL schema init failed: {exc}")


@app.on_event("startup")
def startup_vectorstore():
    """Warm up Pinecone in the background so /ask is faster on first query."""
    import threading

    threading.Thread(target=get_vectorstore, daemon=True).start()

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuthRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class ConversationCreateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    title: str = "New chat"


class MessageCreateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    sender: str = Field(pattern="^(user|assistant)$")
    text: str = Field(min_length=1)


def admin_auth(credentials: HTTPBasicCredentials = Depends(security)):
    valid_user = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    valid_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (valid_user and valid_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@app.get("/")
def home():
    return {
        "message": "TerraLaw BD API is running. Use /ask?question=YOUR_QUESTION",
        "available_acts": sorted({meta["act_name"] for meta in ACT_CATALOG.values()}),
    }


@app.get("/metrics")
def metrics():
    return {
        "runtime_metrics": dict(runtime_metrics),
        "vectorstore_loaded": bool(get_vectorstore()),
    }


@app.get("/track-login")
def track_login(user_id: str, role: str = "user"):
    clean_user = sanitize_user_id(user_id)
    clean_role = "admin" if role == "admin" else "user"
    record_login_event(clean_user, clean_role)
    return {"status": "ok"}


@app.post("/api/auth/register")
def api_register(payload: AuthRequest):
    try:
        return register_user(payload.user_id, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/login")
def api_login(payload: AuthRequest):
    try:
        result = authenticate_user(payload.user_id, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    if payload.user_id == ADMIN_USERNAME and payload.password == ADMIN_PASSWORD:
        record_login_event(payload.user_id, "admin")
    else:
        record_login_event(payload.user_id, "user")
    return result


@app.get("/api/conversations")
def api_list_conversations(user_id: str):
    clean_user = sanitize_user_id(user_id)
    return {"conversations": list_conversations(clean_user)}


@app.post("/api/conversations")
def api_create_conversation(payload: ConversationCreateRequest):
    clean_user = sanitize_user_id(payload.user_id)
    conversation = create_conversation(clean_user, payload.title.strip() or "New chat")
    return conversation


@app.get("/api/conversations/{conversation_id}")
def api_get_conversation(conversation_id: str, user_id: str):
    clean_user = sanitize_user_id(user_id)
    conversation = get_conversation(clean_user, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.post("/api/conversations/{conversation_id}/messages")
def api_add_message(conversation_id: str, payload: MessageCreateRequest):
    clean_user = sanitize_user_id(payload.user_id)
    try:
        return append_message(clean_user, conversation_id, payload.sender, payload.text)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/admin/api/dashboard")
def admin_dashboard_data(_admin: str = Depends(admin_auth)):
    return dashboard_payload(bool(get_vectorstore()))


@app.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(_admin: str = Depends(admin_auth)):
    return DASHBOARD_TEMPLATE.read_text(encoding="utf-8")


@app.get("/ask")
def ask(question: str):
    return answer_question(question)
