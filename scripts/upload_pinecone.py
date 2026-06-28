"""Upload processed legal chunks to Pinecone only (no local embedding)."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from model.core.terralaw_core import build_documents_from_text  # noqa: E402
from model.paths import DATA_PROCESSED_DIR  # noqa: E402
from model.vectorstore.pinecone_store import upsert_documents  # noqa: E402


def load_docs():
    docs = []
    for path in sorted(DATA_PROCESSED_DIR.glob("*_cleaned.txt")):
        text = path.read_text(encoding="utf-8")
        file_docs = build_documents_from_text(path.name, text)
        docs.extend(file_docs)
        print(f"Loaded {path.name}: {len(file_docs)} chunks")
    return docs


def main():
    docs = load_docs()
    print(f"Total chunks: {len(docs)}")
    result = upsert_documents(docs)
    print("Done:", result)


if __name__ == "__main__":
    main()
