from dotenv import load_dotenv

load_dotenv(".env")

from model.core.terralaw_core import analyze_question, build_procedural_guidance
from backend.services.rag import build_search_query, search, answer_question
from backend.config import RERANK_ENABLED, MIN_RELEVANCE_SCORE, MIN_RERANK_SCORE

q = (
    "My father sold part of our family land to an outsider without informing "
    "the other co-sharers. Can I claim pre-emption, and what documents would I need?"
)

analysis = analyze_question(q)
guidance = build_procedural_guidance(analysis)
print("dispute_type:", analysis.dispute_type)
print("confidence:", analysis.confidence)
print("applicable_acts:", analysis.applicable_acts)
print("matched_keywords:", analysis.matched_keywords)
print("search_query:", build_search_query(q, analysis))
print("RERANK_ENABLED:", RERANK_ENABLED)
print("MIN_RELEVANCE_SCORE:", MIN_RELEVANCE_SCORE)
print("MIN_RERANK_SCORE:", MIN_RERANK_SCORE)

results = search(q, analysis)
print("results count:", len(results))
for i, (doc, score) in enumerate(results[:5], 1):
    act = doc.metadata.get("act_name")
    section = doc.metadata.get("section")
    title = (doc.metadata.get("section_title") or "")[:60]
    print(f"  [{i}] score={score:.4f} act={act} section={section} title={title}")

if not results:
    print("NO RESULTS after filtering")

print("\n--- full answer mode ---")
out = answer_question(q)
print("mode:", out["mode"])
print("sources:", len(out.get("sources_used", [])))
print("answer preview:", out["answer"][:400])
