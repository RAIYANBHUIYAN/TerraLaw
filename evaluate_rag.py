import argparse
import json
from datetime import datetime
from pathlib import Path
from statistics import mean

import requests


DEFAULT_API_URL = "http://127.0.0.1:8000/ask"
DEFAULT_CASES_PATH = Path("benchmarks/eval_cases.json")
DEFAULT_REPORTS_DIR = Path("reports")

GROUND_MODES = {"rag", "llm_fallback", "llm_only", "no_context"}


def load_cases(cases_path: Path):
    return json.loads(cases_path.read_text(encoding="utf-8"))


def safe_mean(values):
    return round(mean(values), 3) if values else 0.0


def normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def run_case(api_url: str, case: dict):
    response = requests.get(api_url, params={"question": case["question"]}, timeout=120)
    response.raise_for_status()
    payload = response.json()

    answer = payload.get("answer", "")
    normalized_answer = normalize_text(answer)
    sources = payload.get("sources_used", [])
    analysis = payload.get("analysis") or {}

    acts = {source.get("act_name") for source in sources}
    sections = {str(source.get("section")) for source in sources if source.get("section")}

    required_terms = case.get("required_terms", [])
    required_term_hits = {
        term: normalize_text(term) in normalized_answer
        for term in required_terms
    }

    retrieval_hit = case["expected_act"] in acts
    section_hit = (
        case["expected_section"] in sections
        or f"section {case['expected_section']}" in normalized_answer
    )
    citation_present = "citation:" in normalized_answer
    grounded_mode = payload.get("mode") in GROUND_MODES
    vector_context_used = bool(payload.get("chunks_used"))
    expected_mode_match = payload.get("mode") == case.get("expected_mode")
    safety_notice_present = "safety notice:" in normalized_answer
    dispute_label_present = bool(analysis.get("label"))
    required_term_coverage = safe_mean(1 if hit else 0 for hit in required_term_hits.values()) if required_terms else 0.0

    hallucination_flag = retrieval_hit and not section_hit and citation_present

    return {
        "id": case["id"],
        "question": case["question"],
        "domain": case.get("domain"),
        "mode": payload.get("mode"),
        "retrieval_hit": retrieval_hit,
        "section_hit": section_hit,
        "citation_present": citation_present,
        "grounded_mode": grounded_mode,
        "vector_context_used": vector_context_used,
        "expected_mode_match": expected_mode_match,
        "safety_notice_present": safety_notice_present,
        "dispute_label_present": dispute_label_present,
        "required_term_coverage": required_term_coverage,
        "hallucination_flag": hallucination_flag,
        "required_term_hits": required_term_hits,
        "sources_used": sources,
        "answer_preview": answer[:500],
    }


def summarize(results):
    return {
        "cases": len(results),
        "retrieval_precision": safe_mean([1 if result["retrieval_hit"] else 0 for result in results]),
        "section_accuracy": safe_mean([1 if result["section_hit"] else 0 for result in results]),
        "citation_rate": safe_mean([1 if result["citation_present"] else 0 for result in results]),
        "grounded_response_rate": safe_mean([1 if result["grounded_mode"] else 0 for result in results]),
        "vector_context_rate": safe_mean([1 if result["vector_context_used"] else 0 for result in results]),
        "mode_match_rate": safe_mean([1 if result["expected_mode_match"] else 0 for result in results]),
        "safety_notice_rate": safe_mean([1 if result["safety_notice_present"] else 0 for result in results]),
        "dispute_label_rate": safe_mean([1 if result["dispute_label_present"] else 0 for result in results]),
        "required_term_coverage": safe_mean([result["required_term_coverage"] for result in results]),
        "hallucination_rate": safe_mean([1 if result["hallucination_flag"] else 0 for result in results]),
    }


def write_report(output: dict, reports_dir: Path):
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"metrics_report_{timestamp}.json"
    report_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return report_path


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate TerraLaw BD model metrics.")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Ask endpoint URL.")
    parser.add_argument("--cases", default=str(DEFAULT_CASES_PATH), help="Path to benchmark cases JSON.")
    parser.add_argument("--reports-dir", default=str(DEFAULT_REPORTS_DIR), help="Directory for saved reports.")
    parser.add_argument("--no-save", action="store_true", help="Do not save a JSON report file.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cases_path = Path(args.cases)
    reports_dir = Path(args.reports_dir)

    cases = load_cases(cases_path)
    results = [run_case(args.api_url, case) for case in cases]
    output = {
        "generated_at": datetime.now().isoformat(),
        "api_url": args.api_url,
        "cases_file": str(cases_path),
        "summary": summarize(results),
        "results": results,
    }

    report_path = None
    if not args.no_save:
        report_path = write_report(output, reports_dir)
        output["report_path"] = str(report_path)

    print(json.dumps(output, indent=2))
