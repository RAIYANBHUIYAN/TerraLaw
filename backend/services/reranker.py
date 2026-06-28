from langchain_core.documents import Document

from backend.config import RERANK_MODEL, RERANK_TOP_K

_reranker = None


def get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder

        _reranker = CrossEncoder(RERANK_MODEL)
    return _reranker


def rerank_documents(
    question: str,
    candidates: list[tuple[Document, float]],
    top_k: int = RERANK_TOP_K,
) -> list[tuple[Document, float]]:
    if not candidates:
        return []

    docs = [doc for doc, _ in candidates]
    pairs = [(question, doc.page_content) for doc in docs]
    scores = get_reranker().predict(pairs, show_progress_bar=False)

    ranked = sorted(
        ((doc, float(score)) for doc, score in zip(docs, scores)),
        key=lambda item: item[1],
        reverse=True,
    )
    return ranked[:top_k]
