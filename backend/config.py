import os

import httpx
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

GROQ_MODEL = "llama-3.3-70b-versatile"
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
RETRIEVAL_K = 20
RERANK_TOP_K = 8
RETRIEVAL_RETURN_K = 4
MIN_RELEVANCE_SCORE = 0.35
MIN_RERANK_SCORE = float(os.getenv("MIN_RERANK_SCORE", "-9.0"))

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in .env")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "123")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "").strip()
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "terralaw-bd").strip()
PINECONE_INDEX_HOST = os.getenv("PINECONE_INDEX_HOST", "").strip()
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "").strip()
PINECONE_TEXT_FIELD = os.getenv("PINECONE_TEXT_FIELD", "text").strip()
PINECONE_INTEGRATED = os.getenv("PINECONE_INTEGRATED", "false").lower() in {"1", "true", "yes", "on"}
VECTORSTORE_BACKEND = os.getenv("VECTORSTORE_BACKEND", "auto").strip().lower()

_default_cors = "http://127.0.0.1:3000,http://localhost:3000"
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", _default_cors).split(",")
    if origin.strip()
]

llm_client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
    timeout=httpx.Timeout(3600.0),
)
