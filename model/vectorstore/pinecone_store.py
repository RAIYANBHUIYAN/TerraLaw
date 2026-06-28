"""Pinecone vector store helpers for TerraLaw BD."""

from __future__ import annotations

import hashlib
import os
from typing import Any

from langchain_core.documents import Document

from model.paths import DEFAULT_EMBEDDING_MODEL

UPSERT_BATCH_SIZE = 100
METADATA_TEXT_KEY = "chunk_text"
EMBEDDING_DIMENSION = 384
DEFAULT_NAMESPACE = ""


def is_pinecone_configured() -> bool:
    return bool(os.getenv("PINECONE_API_KEY", "").strip())


def pinecone_integrated_enabled() -> bool:
    return os.getenv("PINECONE_INTEGRATED", "false").lower() in {"1", "true", "yes", "on"}


def pinecone_text_field() -> str:
    return os.getenv("PINECONE_TEXT_FIELD", "text").strip() or "text"


def pinecone_namespace() -> str:
    return os.getenv("PINECONE_NAMESPACE", "").strip()


def _pinecone_client():
    from pinecone import Pinecone

    api_key = os.getenv("PINECONE_API_KEY", "").strip()
    if not api_key:
        raise ValueError("PINECONE_API_KEY is not set.")
    return Pinecone(api_key=api_key)


def _normalize_index_host(host: str) -> str:
    host = host.strip()
    for prefix in ("https://", "http://"):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    return host.rstrip("/")


def get_pinecone_index():
    client = _pinecone_client()
    host = _normalize_index_host(os.getenv("PINECONE_INDEX_HOST", ""))
    if host:
        return client.Index(host=host)

    index_name = os.getenv("PINECONE_INDEX_NAME", "terralaw-bd").strip()
    if not index_name:
        raise ValueError("Set PINECONE_INDEX_NAME or PINECONE_INDEX_HOST.")
    return client.Index(index_name)


def document_id(metadata: dict[str, Any]) -> str:
    raw = (
        f"{metadata.get('source', '')}|"
        f"{metadata.get('section_key', '')}|"
        f"{metadata.get('chunk_index', 0)}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def flatten_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            cleaned[key] = ""
        elif isinstance(value, bool):
            cleaned[key] = value
        elif isinstance(value, (int, float)):
            cleaned[key] = value
        elif isinstance(value, list):
            cleaned[key] = [str(item) for item in value]
        else:
            cleaned[key] = str(value)
    return cleaned


def sanitize_metadata(metadata: dict[str, Any], page_content: str) -> dict[str, Any]:
    cleaned = flatten_metadata(metadata)
    cleaned[METADATA_TEXT_KEY] = page_content
    return cleaned


def embedding_model(model_name: str = DEFAULT_EMBEDDING_MODEL):
    from langchain_community.embeddings import SentenceTransformerEmbeddings

    return SentenceTransformerEmbeddings(model_name=model_name)


def record_from_document(doc: Document) -> dict[str, Any]:
    text_field = pinecone_text_field()
    return {
        "_id": document_id(doc.metadata),
        text_field: doc.page_content,
        **flatten_metadata(doc.metadata),
    }


def _upsert_integrated(
    documents: list[Document],
    *,
    namespace: str,
) -> dict[str, Any]:
    index = get_pinecone_index()
    target_namespace = namespace or pinecone_namespace()
    upserted = 0

    for start in range(0, len(documents), UPSERT_BATCH_SIZE):
        batch_docs = documents[start : start + UPSERT_BATCH_SIZE]
        records = [record_from_document(doc) for doc in batch_docs]
        index.upsert_records(namespace=target_namespace, records=records)
        upserted += len(records)
        print(f"Upserted {upserted}/{len(documents)} records to Pinecone (integrated).")

    stats = index.describe_index_stats()
    return {
        "upserted": upserted,
        "namespace": target_namespace or "(default)",
        "total_vector_count": stats.total_vector_count,
        "mode": "integrated",
    }


def _upsert_dense(
    documents: list[Document],
    *,
    embedding_model_name: str,
    namespace: str,
) -> dict[str, Any]:
    index = get_pinecone_index()
    embedder = embedding_model(embedding_model_name)
    target_namespace = namespace or pinecone_namespace()
    upserted = 0

    for start in range(0, len(documents), UPSERT_BATCH_SIZE):
        batch_docs = documents[start : start + UPSERT_BATCH_SIZE]
        batch_texts = [doc.page_content for doc in batch_docs]
        batch_embeddings = embedder.embed_documents(batch_texts)
        batch_vectors: list[dict[str, Any]] = []

        for doc, values in zip(batch_docs, batch_embeddings):
            batch_vectors.append(
                {
                    "id": document_id(doc.metadata),
                    "values": values,
                    "metadata": sanitize_metadata(doc.metadata, doc.page_content),
                }
            )

        index.upsert(vectors=batch_vectors, namespace=target_namespace)
        upserted += len(batch_vectors)
        print(f"Upserted {upserted}/{len(documents)} vectors to Pinecone (dense).")

    stats = index.describe_index_stats()
    return {
        "upserted": upserted,
        "namespace": target_namespace or "(default)",
        "total_vector_count": stats.total_vector_count,
        "mode": "dense",
    }


def upsert_documents(
    documents: list[Document],
    *,
    embedding_model_name: str = DEFAULT_EMBEDDING_MODEL,
    namespace: str = "",
) -> dict[str, Any]:
    if not documents:
        return {"upserted": 0, "namespace": namespace or "(default)"}

    if pinecone_integrated_enabled():
        return _upsert_integrated(documents, namespace=namespace)
    return _upsert_dense(
        documents,
        embedding_model_name=embedding_model_name,
        namespace=namespace,
    )


class PineconeVectorStore:
    """Query interface compatible with TerraLaw RAG retrieval."""

    def __init__(self, *, embedding_model_name: str = DEFAULT_EMBEDDING_MODEL, namespace: str = ""):
        self.index = get_pinecone_index()
        self.namespace = namespace or pinecone_namespace()
        self.text_field = pinecone_text_field()
        self.embedding_model_name = embedding_model_name
        self.integrated = pinecone_integrated_enabled()
        self._embedder = None

    def _get_embedder(self):
        if self._embedder is None:
            self._embedder = embedding_model(self.embedding_model_name)
        return self._embedder

    def _search_integrated(
        self,
        query: str,
        k: int,
        act_names: set[str] | None,
    ) -> list[tuple[Document, float]]:
        query_payload: dict[str, Any] = {
            "inputs": {"text": query},
            "top_k": k,
        }
        if act_names:
            query_payload["filter"] = {"act_name": {"$in": sorted(act_names)}}

        response = self.index.search(
            namespace=self.namespace,
            query=query_payload,
            fields=[
                self.text_field,
                "source",
                "act_name",
                "act_year",
                "section",
                "section_title",
                "chapter",
                "part",
                "chunk_index",
                "chunk_count",
            ],
        )

        results: list[tuple[Document, float]] = []
        hits = getattr(response, "result", None)
        hits = getattr(hits, "hits", None) if hits is not None else None
        if hits is None and isinstance(response, dict):
            hits = response.get("result", {}).get("hits", [])

        for hit in hits or []:
            if isinstance(hit, dict):
                hit_id = hit.get("_id", "")
                score = float(hit.get("_score", 0.0))
                fields = hit.get("fields", {})
            else:
                hit_id = getattr(hit, "_id", "")
                score = float(getattr(hit, "_score", 0.0) or 0.0)
                fields = getattr(hit, "fields", {}) or {}

            if not isinstance(fields, dict):
                fields = dict(fields)

            page_content = str(fields.pop(self.text_field, "") or "")
            metadata = flatten_metadata(fields)
            if hit_id:
                metadata["pinecone_id"] = str(hit_id)
            results.append((Document(page_content=page_content, metadata=metadata), score))

        return results

    def _search_dense(
        self,
        query: str,
        k: int,
        act_names: set[str] | None,
    ) -> list[tuple[Document, float]]:
        filter_dict = None
        if act_names:
            filter_dict = {"act_name": {"$in": sorted(act_names)}}

        query_vector = self._get_embedder().embed_query(query)
        response = self.index.query(
            vector=query_vector,
            top_k=k,
            include_metadata=True,
            filter=filter_dict,
            namespace=self.namespace,
        )

        results: list[tuple[Document, float]] = []
        for match in response.matches or []:
            metadata = dict(match.metadata or {})
            page_content = metadata.pop(METADATA_TEXT_KEY, "")
            doc = Document(page_content=page_content, metadata=metadata)
            results.append((doc, float(match.score or 0.0)))
        return results

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 4,
        *,
        act_names: set[str] | None = None,
    ) -> list[tuple[Document, float]]:
        if self.integrated:
            return self._search_integrated(query, k, act_names)
        return self._search_dense(query, k, act_names)
