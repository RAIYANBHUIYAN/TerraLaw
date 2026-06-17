import argparse
import hashlib
import json
import os
import pickle
from datetime import datetime
from pathlib import Path

from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_community.vectorstores import InMemoryVectorStore

from terralaw_core import build_documents_from_text


DEFAULT_PROCESSED_DATA_DIR = Path("Proessed_data")
DEFAULT_VECTOR_DIR = Path("vectorstore")
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_processed_data(processed_data_dir: str | Path = DEFAULT_PROCESSED_DATA_DIR):
    docs = []
    processed_path = Path(processed_data_dir)

    if not processed_path.exists():
        print(f"Directory {processed_path} does not exist.")
        return docs

    for path in sorted(processed_path.glob("*_cleaned.txt")):
        try:
            full_text = path.read_text(encoding="utf-8")
            file_docs = build_documents_from_text(path.name, full_text)
            docs.extend(file_docs)
            print(f"Indexed {path.name}: {len(file_docs)} chunks")
        except Exception as exc:
            print(f"Error reading {path.name}: {exc}")

    return docs


def _embedding_model(model_name: str = DEFAULT_EMBEDDING_MODEL):
    return SentenceTransformerEmbeddings(model_name=model_name)


def _source_manifest(processed_data_dir: Path) -> list[dict]:
    manifest = []
    for path in sorted(processed_data_dir.glob("*_cleaned.txt")):
        stat = path.stat()
        manifest.append(
            {
                "name": path.name,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "sha256": _file_sha256(path),
            }
        )
    return manifest


def build_vectorstore(
    processed_data_dir: str | Path = DEFAULT_PROCESSED_DATA_DIR,
    vector_dir: str | Path = DEFAULT_VECTOR_DIR,
    embedding_model_name: str = DEFAULT_EMBEDDING_MODEL,
):
    processed_path = Path(processed_data_dir)
    vector_path = Path(vector_dir)
    vector_path.mkdir(parents=True, exist_ok=True)

    docs = load_processed_data(processed_path)
    print("Total chunks:", len(docs))

    db = InMemoryVectorStore(embedding=_embedding_model(embedding_model_name))
    if docs:
        db.add_documents(docs)

    embeddings_path = vector_path / "embeddings.pkl"
    documents_path = vector_path / "documents.pkl"
    metadata_path = vector_path / "metadata.json"

    with embeddings_path.open("wb") as handle:
        pickle.dump(db, handle)

    with documents_path.open("wb") as handle:
        pickle.dump(docs, handle)

    metadata = {
        "generated_at": datetime.now().isoformat(),
        "processed_data_dir": str(processed_path),
        "vector_dir": str(vector_path),
        "embedding_model_name": embedding_model_name,
        "document_count": len(docs),
        "artifact_files": {
            "embeddings": str(embeddings_path),
            "documents": str(documents_path),
        },
        "source_manifest": _source_manifest(processed_path),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print("Vectorstore saved successfully!")
    return metadata


def parse_args():
    parser = argparse.ArgumentParser(description="Build the TerraLaw BD vectorstore.")
    parser.add_argument(
        "--processed-data-dir",
        default=str(DEFAULT_PROCESSED_DATA_DIR),
        help="Directory containing cleaned legal text files.",
    )
    parser.add_argument(
        "--vector-dir",
        default=str(DEFAULT_VECTOR_DIR),
        help="Directory where the vectorstore artifacts will be written.",
    )
    parser.add_argument(
        "--embedding-model-name",
        default=DEFAULT_EMBEDDING_MODEL,
        help="Embedding model used to generate vector representations.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build_vectorstore(
        processed_data_dir=args.processed_data_dir,
        vector_dir=args.vector_dir,
        embedding_model_name=args.embedding_model_name,
    )
