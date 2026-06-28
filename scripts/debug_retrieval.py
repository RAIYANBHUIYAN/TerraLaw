from dotenv import load_dotenv

load_dotenv(".env")

from model.core.terralaw_core import analyze_question
from backend.services.rag import build_search_query
from backend.services.vectorstore import get_vectorstore
from backend.config import RETRIEVAL_K

q = (
    "My father sold part of our family land to an outsider without informing "
    "the other co-sharers. Can I claim pre-emption, and what documents would I need?"
)
analysis = analyze_question(q)
search_query = build_search_query(q, analysis)
store = get_vectorstore()

print("=== scoped (with act filter) ===")
scoped = store.similarity_search_with_score(
    search_query, k=RETRIEVAL_K, act_names=set(analysis.applicable_acts)
)
for i, (doc, score) in enumerate(scoped[:8], 1):
    print(f"{i}. score={score:.4f} section={doc.metadata.get('section')} act={doc.metadata.get('act_name')}")

print("\n=== fallback (no act filter) ===")
fallback = store.similarity_search_with_score(search_query, k=RETRIEVAL_K, act_names=None)
for i, (doc, score) in enumerate(fallback[:8], 1):
    print(f"{i}. score={score:.4f} section={doc.metadata.get('section')} act={doc.metadata.get('act_name')}")

# grep section 96 in pinecone via search for pre-emption specifically
print("\n=== query: section 96 pre-emption SAT ===")
direct = store.similarity_search_with_score(
    "section 96 pre-emption co-sharer State Acquisition and Tenancy Act",
    k=5,
    act_names={"State Acquisition and Tenancy Act"},
)
for i, (doc, score) in enumerate(direct, 1):
    print(f"{i}. score={score:.4f} section={doc.metadata.get('section')} title={(doc.metadata.get('section_title') or '')[:50]}")
