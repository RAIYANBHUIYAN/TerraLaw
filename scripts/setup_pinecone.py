"""Verify the Pinecone integrated index and print connection details."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from model.vectorstore.pinecone_store import (  # noqa: E402
    get_pinecone_index,
    is_pinecone_configured,
    pinecone_integrated_enabled,
    pinecone_namespace,
    pinecone_text_field,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Verify the TerraLaw Pinecone integrated index."
    )
    parser.add_argument(
        "--index-name",
        default=os.getenv("PINECONE_INDEX_NAME", "terralaw-bd"),
        help="Pinecone index name.",
    )
    return parser.parse_args()


def main():
    if not is_pinecone_configured():
        print("Error: PINECONE_API_KEY is not set in .env")
        sys.exit(1)

    args = parse_args()
    client = get_pinecone_index()
    stats = client.describe_index_stats()

    from pinecone import Pinecone

    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY", "").strip())
    description = pc.describe_index(args.index_name)
    host = description.host

    print()
    print("Pinecone setup check complete.")
    print(f"  Index name:      {args.index_name}")
    print(f"  Index host:      {host}")
    print(f"  Integrated:      {pinecone_integrated_enabled()}")
    print(f"  Text field:      {pinecone_text_field()}")
    print(f"  Namespace:       {pinecone_namespace()}")
    print(f"  Vector count:    {stats.total_vector_count}")
    print()
    print("Add or confirm these in your .env:")
    print(f"  PINECONE_INDEX_NAME={args.index_name}")
    print(f"  PINECONE_INDEX_HOST={host}")
    print("  PINECONE_TEXT_FIELD=text")
    print("  PINECONE_INTEGRATED=true")
    print("  VECTORSTORE_BACKEND=pinecone")
    print()
    print("Then upload statute chunks:")
    print("  python scripts/build_index.py")


if __name__ == "__main__":
    main()
