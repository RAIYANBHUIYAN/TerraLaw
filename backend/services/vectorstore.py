import pickle
from typing import Protocol

from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_community.vectorstores import InMemoryVectorStore
from langchain_core.documents import Document

from backend.config import PINECONE_NAMESPACE, VECTORSTORE_BACKEND
from model.paths import DEFAULT_EMBEDDING_MODEL, VECTORSTORE_DIR

_vectorstore: "VectorStoreBackend | None" = None
_vectorstore_checked = False


class VectorStoreBackend(Protocol):
    def similarity_search_with_score(
        self,
        query: str,
        k: int = 4,
        *,
        act_names: set[str] | None = None,
    ) -> list[tuple[Document, float]]: ...


class LocalVectorStore:
    def __init__(self, store: InMemoryVectorStore):
        self._store = store

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 4,
        *,
        act_names: set[str] | None = None,
    ) -> list[tuple[Document, float]]:
        filter_fn = None
        if act_names:
            applicable = set(act_names)
            filter_fn = lambda doc: doc.metadata.get("act_name") in applicable

        try:
            return self._store.similarity_search_with_score(
                query,
                k=k,
                filter=filter_fn,
            )
        except TypeError:
            results = self._store.similarity_search_with_score(query, k=k)
            if filter_fn:
                results = [(doc, score) for doc, score in results if filter_fn(doc)]
            return results


def _embedding_model():
    return SentenceTransformerEmbeddings(model_name=DEFAULT_EMBEDDING_MODEL)


def _load_local_inmemory_store() -> InMemoryVectorStore | None:
    try:
        with open(VECTORSTORE_DIR / "embeddings.pkl", "rb") as handle:
            return pickle.load(handle)
    except Exception as exc:
        print("Error loading vectorstore:", exc)

    try:
        with open(VECTORSTORE_DIR / "documents.pkl", "rb") as handle:
            docs = pickle.load(handle)

        rebuilt_db = InMemoryVectorStore(embedding=_embedding_model())
        if docs:
            rebuilt_db.add_documents(docs)
        print(f"Rebuilt vectorstore from documents.pkl with {len(docs)} chunks.")
        return rebuilt_db
    except Exception as exc:
        print("Error rebuilding vectorstore from documents.pkl:", exc)
        return None


def _load_pinecone_store() -> VectorStoreBackend | None:
    try:
        from model.vectorstore.pinecone_store import PineconeVectorStore

        store = PineconeVectorStore(
            embedding_model_name=DEFAULT_EMBEDDING_MODEL,
            namespace=PINECONE_NAMESPACE,
        )
        stats = store.index.describe_index_stats()
        print(
            f"Pinecone vectorstore ready "
            f"(total vectors: {stats.total_vector_count}, "
            f"namespace: {PINECONE_NAMESPACE or 'default'})."
        )
        return store
    except Exception as exc:
        print("Error loading Pinecone vectorstore:", exc)
        return None


def load_vectorstore() -> VectorStoreBackend | None:
    backend = VECTORSTORE_BACKEND

    if backend in {"pinecone", "auto"}:
        pinecone_store = _load_pinecone_store()
        if pinecone_store:
            return pinecone_store
        if backend == "pinecone":
            print("VECTORSTORE_BACKEND=pinecone but Pinecone is unavailable.")
            return None

    local_store = _load_local_inmemory_store()
    if local_store:
        print("Using local pickle vectorstore.")
        return LocalVectorStore(local_store)

    return None


def get_vectorstore() -> VectorStoreBackend | None:
    """Load vectorstore on first use so the API can start quickly."""
    global _vectorstore, _vectorstore_checked
    if not _vectorstore_checked:
        print("Loading vectorstore...")
        _vectorstore = load_vectorstore()
        _vectorstore_checked = True
    return _vectorstore


def preload_vectorstore() -> VectorStoreBackend | None:
    return get_vectorstore()
