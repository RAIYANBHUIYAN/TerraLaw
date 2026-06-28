"""Quick Pinecone connectivity and search test for TerraLaw BD."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from model.vectorstore.pinecone_store import (  # noqa: E402
    PineconeVectorStore,
    get_pinecone_index,
    is_pinecone_configured,
    pinecone_namespace,
)


def main():
    print("=== TerraLaw Pinecone Test ===\n")

    if not is_pinecone_configured():
        print("FAIL: PINECONE_API_KEY is not set in .env")
        sys.exit(1)

    print("1. Connecting to index...")
    try:
        index = get_pinecone_index()
        stats = index.describe_index_stats()
        print(f"   OK - connected")
        print(f"   Total vectors: {stats.total_vector_count}")
        print(f"   Namespace:     {pinecone_namespace()}")
        if hasattr(stats, "namespaces") and stats.namespaces:
            for ns, ns_stats in stats.namespaces.items():
                count = getattr(ns_stats, "vector_count", ns_stats)
                print(f"   - {ns!r}: {count} vectors")
    except Exception as exc:
        print(f"   FAIL: {exc}")
        sys.exit(1)

    vector_count = stats.total_vector_count or 0
    if vector_count == 0:
        print("\n2. Index is EMPTY - run: python scripts/build_index.py")
        sys.exit(2)

    print("\n2. Running test search...")
    query = "right of pre-emption under State Acquisition and Tenancy Act"
    try:
        store = PineconeVectorStore()
        results = store.similarity_search_with_score(query, k=3)
    except Exception as exc:
        print(f"   FAIL: {exc}")
        sys.exit(1)

    if not results:
        print("   FAIL: search returned 0 results")
        sys.exit(1)

    print(f"   OK - got {len(results)} result(s) for query:")
    print(f'   "{query}"\n')
    for i, (doc, score) in enumerate(results, start=1):
        act = doc.metadata.get("act_name", "?")
        section = doc.metadata.get("section", "?")
        preview = doc.page_content[:120].replace("\n", " ")
        print(f"   [{i}] score={score:.4f} | {act} | section {section}")
        print(f"       {preview}...")

    print("\n=== Pinecone is working ===")


if __name__ == "__main__":
    main()
