import re
from datetime import datetime

import openai

from model.core.terralaw_core import (
    QuestionAnalysis,
    analyze_question,
    build_citations_block,
    build_procedural_guidance,
    format_source_label,
    summarize_sources,
)

from backend.config import (
    GROQ_MODEL,
    LLM_TEMPERATURE,
    MIN_RERANK_SCORE,
    MIN_RELEVANCE_SCORE,
    RERANK_ENABLED,
    RERANK_TOP_K,
    RETRIEVAL_K,
    RETRIEVAL_RETURN_K,
    llm_client,
)
from backend.services.dashboard import extract_usage, record_request_event
from backend.services.reranker import rerank_documents
from backend.services.vectorstore import get_vectorstore
from backend.state import runtime_metrics


def response_text(response) -> str:
    return str(getattr(response, "output_text", None) or getattr(response, "output", "") or "").strip()


def _section_numbers_in_question(question: str) -> set[str]:
    return {
        match.group(1)
        for match in re.finditer(r"\bsection\s+(\d+[a-z]?)\b", question, re.IGNORECASE)
    }


def filter_results_by_score(
    question: str,
    results_with_scores,
    *,
    min_score: float | None = None,
    analysis: QuestionAnalysis | None = None,
):
    threshold = min_score if min_score is not None else MIN_RELEVANCE_SCORE
    query_terms = {
        term for term in re.findall(r"[a-zA-Z0-9]+", question.lower()) if len(term) > 3
    }
    requested_sections = _section_numbers_in_question(question)
    key_sections: set[str] = set()
    if analysis and analysis.dispute_type == "preemption":
        key_sections.update({"95", "96"})
    elif analysis and analysis.dispute_type == "land_acquisition":
        key_sections.update({"4", "5", "6"})

    rescored = []
    for doc, score in results_with_scores:
        if score < threshold:
            continue
        doc_terms = set(re.findall(r"[a-zA-Z0-9]+", doc.page_content.lower()))
        overlap_bonus = len(query_terms & doc_terms) * 0.02
        section_bonus = 0.0
        section_number = str(doc.metadata.get("section", "")).lower()
        if requested_sections and section_number in {item.lower() for item in requested_sections}:
            section_bonus = 0.08
        elif key_sections and section_number in {item.lower() for item in key_sections}:
            section_bonus = 0.12
        rescored.append((doc, score + overlap_bonus + section_bonus))

    rescored.sort(key=lambda item: item[1], reverse=True)
    return rescored[:RETRIEVAL_RETURN_K]


def apply_reranking(question: str, candidates: list[tuple]) -> tuple[list[tuple], bool]:
    if not RERANK_ENABLED or not candidates:
        return candidates, False

    try:
        runtime_metrics["rerank_attempts"] += 1
        reranked = rerank_documents(question, candidates, top_k=RERANK_TOP_K)
        runtime_metrics["rerank_successes"] += 1
        return reranked, True
    except Exception as exc:
        runtime_metrics["rerank_failures"] += 1
        print(f"Reranking failed, falling back to vector scores: {exc}")
        return candidates[:RERANK_TOP_K], False


def create_llm_response(messages: list[dict[str, str]]):
    return llm_client.responses.create(
        model=GROQ_MODEL,
        input=messages,
        temperature=LLM_TEMPERATURE,
    )


TERRALAW_SYSTEM_PROMPT = """
You are TerraLaw BD — a warm, plain-language guide to Bangladeshi land law.

Personality:
- Sound like a knowledgeable, friendly person helping a neighbour understand their options.
- Be calm and reassuring. Land issues are stressful; acknowledge that briefly when it fits.
- Use "you" and everyday English. Explain legal terms the first time you use them.
- Write in flowing paragraphs, not legal memos. Vary how you open answers — never start two answers the same way.

How to answer:
- Lead with the direct answer in 1–2 short paragraphs.
- For every legal rule or right you mention, cite the exact Act and section from the retrieved sources (e.g. "Under Section 96 of the State Acquisition and Tenancy Act, 1950…").
- Use the section numbers and act names exactly as shown in the retrieved source labels — do not invent citations.
- Add practical next steps only when they genuinely help — office to visit, documents to gather, type of lawyer to consult.
- Use bullets sparingly and only for steps or document lists.
- Keep narrow questions short. Expand only when the user asks something broad or practical.

Strict rules:
- You are not a lawyer. Never claim to give legal advice or guarantee an outcome.
- Base statutory conclusions only on the retrieved context provided. Do not invent sections, deadlines, or procedures.
- If the context does not cover the question, say so honestly and suggest what records or professional help would clarify it.
- Do not use rigid headings like "Issue", "Short Answer", "Applicable Law", "Procedure", or "Safety Notice".
- Do not add your own "Sources cited" block at the end — the system appends official citations separately.
- End every answer with one brief, natural sentence noting this is informational only and not a substitute for advice from a licensed legal professional.
""".strip()


def build_rag_messages(question: str, guidance: dict, context: str) -> list[dict[str, str]]:
    applicable_acts = ", ".join(guidance["applicable_acts"]) or "Use the retrieved sources only"
    matched_keywords = ", ".join(guidance["matched_keywords"]) or "None"

    user_prompt = f"""
Background for this question (use as hints, not as facts to invent):
- Likely topic: {guidance["label"]}
- Confidence: {guidance["confidence"]}
- Likely relevant acts: {applicable_acts}
- Keywords spotted: {matched_keywords}
- Where people usually start: {guidance["suggested_authority"]}
- Typical forum if a case is needed: {guidance["suggested_forum"]}
- Lawyer type that often helps: {guidance["suggested_lawyer_type"]}

Retrieved statutory text (your only source for legal conclusions):
{context}

User question:
{question}

Reply in a natural, friendly voice. Answer the question directly first.
When stating a legal rule, always name the Act and Section number from the retrieved sources.
""".strip()

    return [
        {"role": "system", "content": TERRALAW_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def build_fallback_messages(question: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": TERRALAW_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"{question}\n\n"
                "No statute text was retrieved for this question. "
                "If you cannot answer reliably from general knowledge, say so plainly "
                "and suggest checking the relevant land office records or speaking with "
                "a licensed legal professional."
            ),
        },
    ]


def build_search_query(question: str, analysis: QuestionAnalysis) -> str:
    extras = []
    if analysis.matched_keywords:
        extras.extend(analysis.matched_keywords)
    if analysis.applicable_acts:
        extras.extend(analysis.applicable_acts)
    if analysis.dispute_type == "land_acquisition":
        extras.extend(["objection", "notice", "section 4"])
    if analysis.dispute_type == "preemption":
        extras.extend(["pre-emption", "pre emption", "right of pre-emption", "co-sharer", "section 96"])
    return " ".join([question] + extras)


def search(question: str, analysis: QuestionAnalysis):
    vectorstore = get_vectorstore()
    if not vectorstore:
        return []

    search_query = build_search_query(question, analysis)
    act_names = set(analysis.applicable_acts) if analysis.applicable_acts else None

    scoped = vectorstore.similarity_search_with_score(
        search_query,
        k=RETRIEVAL_K,
        act_names=act_names,
    )

    reranked, used_rerank = apply_reranking(question, scoped)
    # Cross-encoder reranker scores are logits (often negative for legal text),
    # not comparable to cosine similarity — trust rerank order instead.
    if used_rerank:
        filtered = filter_results_by_score(
            question, reranked, min_score=float("-inf"), analysis=analysis
        )
    else:
        filtered = filter_results_by_score(
            question, reranked, min_score=MIN_RELEVANCE_SCORE, analysis=analysis
        )
    if filtered or not analysis.applicable_acts:
        return filtered

    fallback = vectorstore.similarity_search_with_score(
        search_query,
        k=RETRIEVAL_K,
        act_names=None,
    )
    reranked, used_rerank = apply_reranking(question, fallback)
    if used_rerank:
        return filter_results_by_score(
            question, reranked, min_score=float("-inf"), analysis=analysis
        )
    return filter_results_by_score(
        question, reranked, min_score=MIN_RELEVANCE_SCORE, analysis=analysis
    )


def append_citations(answer: str, sources_used: list[dict]) -> str:
    citations = build_citations_block(sources_used)
    if not citations:
        return answer
    if citations in answer:
        return answer
    return f"{answer.rstrip()}\n\n{citations}"


def build_context(results_with_scores):
    context_blocks = []
    for index, (doc, score) in enumerate(results_with_scores, start=1):
        label = format_source_label(doc.metadata)
        context_blocks.append(
            f"[Source {index} | score={score:.3f} | {label}]\n{doc.page_content}"
        )
    return "\n\n".join(context_blocks)


def vectorstore_only_answer(question: str, analysis: QuestionAnalysis, results_with_scores):
    guidance = build_procedural_guidance(analysis)
    if not results_with_scores:
        return (
            "I couldn't find a strong match in the statutes I have on file for that question.\n\n"
            f"This looks like it may relate to {guidance['label'].lower()}. "
            f"A good first step would be to check with {guidance['suggested_authority']}, "
            f"and if you need formal help, a {guidance['suggested_lawyer_type'].lower()} "
            "can review your documents in detail.\n\n"
            "Please remember this is general information only — not a substitute for "
            "advice from a licensed legal professional."
        )

    top_points = []
    for doc, score in results_with_scores[:3]:
        label = format_source_label(doc.metadata)
        excerpt = doc.page_content.strip().replace("\n", " ")
        top_points.append(f"• {label}: {excerpt[:260]}")

    procedure_lines = "\n".join(f"• {step}" for step in guidance["procedure_steps"][:3])
    document_lines = "\n".join(f"• {item}" for item in guidance["required_documents"][:4])

    return (
        "I'm answering from the statute text directly — the AI summariser isn't available "
        "right now, but here's what the retrieved sections say.\n\n"
        f"Based on your question, this likely falls under {guidance['label'].lower()}.\n\n"
        "Here's the most relevant statutory text I found:\n"
        + "\n".join(top_points)
        + "\n\nIf you're figuring out what to do next:\n"
        + procedure_lines
        + "\n\nPractical next steps:\n"
        + f"• Forum to consider: {guidance['suggested_forum']}\n"
        + f"• Authority to check first: {guidance['suggested_authority']}\n"
        + f"• Type of lawyer who can help: {guidance['suggested_lawyer_type']}\n"
        + "\n\nDocuments worth gathering:\n"
        + document_lines
        + "\n\nThis is informational only — please consult a licensed legal professional "
        "for advice on your specific situation."
    )


def fallback_answer(question: str):
    return create_llm_response(build_fallback_messages(question))


def record_source_metrics(results_with_scores):
    for doc, _ in results_with_scores:
        act_name = doc.metadata.get("act_name")
        if act_name:
            runtime_metrics[f"act:{act_name}"] += 1


def answer_question(question: str) -> dict:
    started_at = datetime.now()
    runtime_metrics["queries"] += 1
    analysis = analyze_question(question)
    guidance = build_procedural_guidance(analysis)
    vectorstore = get_vectorstore()

    if not vectorstore:
        runtime_metrics["vectorstore_unavailable"] += 1
        try:
            response = fallback_answer(question)
            answer = response_text(response)
            token_usage = extract_usage(response, question, answer)
            runtime_metrics["llm_only_answers"] += 1
            record_request_event(
                guidance["label"],
                "llm_only",
                (datetime.now() - started_at).total_seconds() * 1000,
                token_usage,
                "ok",
            )
            return {
                "answer": answer,
                "mode": "llm_only",
                "analysis": guidance,
                "chunks_used": [],
                "sources_used": [],
            }
        except openai.PermissionDeniedError as exc:
            record_request_event(
                guidance["label"],
                "error",
                (datetime.now() - started_at).total_seconds() * 1000,
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "permission_denied",
            )
            return {
                "answer": (
                    "The vectorstore is unavailable and Groq rejected the request with 403, "
                    f"so no answer can be generated right now. Details: {exc}"
                ),
                "mode": "error",
                "analysis": guidance,
                "chunks_used": [],
                "sources_used": [],
            }

    results_with_scores = search(question, analysis)
    record_source_metrics(results_with_scores)
    sources_used = summarize_sources(results_with_scores)

    if not results_with_scores:
        runtime_metrics["low_relevance_queries"] += 1
        try:
            response = fallback_answer(question)
            answer = response_text(response)
            token_usage = extract_usage(response, question, answer)
            runtime_metrics["llm_fallback_answers"] += 1
            record_request_event(
                guidance["label"],
                "llm_fallback",
                (datetime.now() - started_at).total_seconds() * 1000,
                token_usage,
                "ok",
            )
            return {
                "answer": answer,
                "mode": "llm_fallback",
                "analysis": guidance,
                "chunks_used": [],
                "sources_used": [],
            }
        except openai.PermissionDeniedError:
            record_request_event(
                guidance["label"],
                "no_context",
                (datetime.now() - started_at).total_seconds() * 1000,
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "permission_denied",
            )
            return {
                "answer": (
                    "No sufficiently relevant statutory chunks were found, and Groq is currently unavailable."
                ),
                "mode": "no_context",
                "analysis": guidance,
                "chunks_used": [],
                "sources_used": [],
            }

    context = build_context(results_with_scores)
    messages = build_rag_messages(question, guidance, context)

    try:
        response = create_llm_response(messages)
        answer = append_citations(response_text(response), sources_used)
        token_usage = extract_usage(response, messages[-1]["content"], answer)
        runtime_metrics["rag_answers"] += 1
        mode = "rag"
        status_label = "ok"
    except openai.PermissionDeniedError:
        runtime_metrics["vector_only_fallback_answers"] += 1
        answer = append_citations(
            vectorstore_only_answer(question, analysis, results_with_scores),
            sources_used,
        )
        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        mode = "vector_only"
        status_label = "permission_denied"
    except Exception as exc:
        runtime_metrics["llm_errors"] += 1
        answer = append_citations(
            (
                "The language model request failed, so the system is returning grounded statutory guidance only.\n\n"
                + vectorstore_only_answer(question, analysis, results_with_scores)
                + f"\n\nSystem note: {exc}"
            ),
            sources_used,
        )
        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        mode = "vector_only"
        status_label = "llm_error"

    if answer and "information not found" in answer.lower():
        runtime_metrics["insufficient_context_answers"] += 1

    record_request_event(
        guidance["label"],
        mode,
        (datetime.now() - started_at).total_seconds() * 1000,
        token_usage,
        status_label,
    )

    return {
        "answer": answer,
        "mode": mode,
        "analysis": guidance,
        "chunks_used": [doc.page_content for doc, _ in results_with_scores],
        "sources_used": sources_used,
    }
