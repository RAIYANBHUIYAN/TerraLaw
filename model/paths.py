from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
DATA_PROCESSED_DIR = DATA_DIR / "processed"
DATA_RAW_DIR = DATA_DIR / "raw"
APP_DATA_DIR = DATA_DIR / "app"

MODEL_DIR = PROJECT_ROOT / "model"
VECTORSTORE_DIR = MODEL_DIR / "vectorstore"
BENCHMARKS_DIR = MODEL_DIR / "benchmarks"
MODEL_REPORTS_DIR = MODEL_DIR / "reports"
MLOPS_RUNS_DIR = MODEL_REPORTS_DIR / "mlops_runs"

BACKEND_REPORTS_DIR = PROJECT_ROOT / "backend" / "reports"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_API_ASK_URL = f"{DEFAULT_API_BASE_URL}/ask"
