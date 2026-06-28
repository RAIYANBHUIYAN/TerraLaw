from dotenv import load_dotenv

load_dotenv(".env")

from model.core.terralaw_core import analyze_question
from backend.services.rag import build_search_query, apply_reranking, filter_results_by_score
from backend.services.vectorstore import get_vectorstore
from backend.config import RETRIEVAL_K, MIN_RERANK_SCORE, MIN_RELEVANCE_SCORE

q = (
    "My father sold part of our family land to an outsider without informing "
    "the other co-sharers. Can I claim pre-emption, and what documents would I need?"
)
analysis = analyze_question(q)
search_query = build_search_query(q, analysis)
store = get_vectorstore()

scoped = store.similarity_search_with_score(
    search_query, k=RETRIEVAL_K, act_names=set(analysis.applicable_acts)
)
print(f"raw candidates: {len(scoped)}")
print("top raw:", [(d.metadata.get("section"), round(s, 4)) for d, s in scoped[:5]])

reranked, used_rerank = apply_reranking(q, scoped)
print(f"used_rerank: {used_rerank}")
print("after rerank top 8:")
for doc, score in reranked[:8]:
    print(f"  section={doc.metadata.get('section')} score={score:.4f}")

threshold = MIN_RERANK_SCORE if used_rerank else MIN_RELEVANCE_SCORE
print(f"threshold: {threshold}")

filtered = filter_results_by_score(q, reranked, min_score=threshold)
print(f"after filter: {len(filtered)}")

# try with lower threshold
filtered2 = filter_results_by_score(q, reranked, min_score=-10)
print(f"after filter (threshold -10): {len(filtered2)}")
