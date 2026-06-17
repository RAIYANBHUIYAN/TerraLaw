from fastapi import Depends, FastAPI, HTTPException, status
import os
import json
import pickle
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
import re
import secrets

import httpx
import openai
from dotenv import load_dotenv
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_community.vectorstores import InMemoryVectorStore
from openai import OpenAI

from model.paths import BACKEND_REPORTS_DIR, MODEL_REPORTS_DIR, VECTORSTORE_DIR
from model.terralaw_core import (
    ACT_CATALOG,
    QuestionAnalysis,
    analyze_question,
    build_procedural_guidance,
    format_source_label,
    summarize_sources,
)


load_dotenv()

GROQ_MODEL = "llama-3.3-70b-versatile"
RETRIEVAL_K = 8
RETRIEVAL_RETURN_K = 4
MIN_RELEVANCE_SCORE = 0.35
REPORTS_DIR = BACKEND_REPORTS_DIR
RUNTIME_DASHBOARD_FILE = REPORTS_DIR / "runtime_dashboard.json"

runtime_metrics: Counter[str] = Counter()
security = HTTPBasic()


def _embedding_model():
    return SentenceTransformerEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )


def _load_vectorstore() -> InMemoryVectorStore | None:
    try:
        with open(VECTORSTORE_DIR / "embeddings.pkl", "rb") as f:
            return pickle.load(f)
    except Exception as exc:
        print("Error loading vectorstore:", exc)

    try:
        with open(VECTORSTORE_DIR / "documents.pkl", "rb") as f:
            docs = pickle.load(f)

        rebuilt_db = InMemoryVectorStore(embedding=_embedding_model())
        if docs:
            rebuilt_db.add_documents(docs)
        print(f"Rebuilt vectorstore from documents.pkl with {len(docs)} chunks.")
        return rebuilt_db
    except Exception as exc:
        print("Error rebuilding vectorstore from documents.pkl:", exc)
        return None


db = _load_vectorstore()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in .env")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "123")

app = FastAPI(title="TerraLaw BD API")

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
    timeout=httpx.Timeout(3600.0),
)


def _default_dashboard_store():
    return {
        "request_log": [],
        "login_events": [],
        "token_totals": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
        "model_usage": {},
        "mode_usage": {},
        "dispute_usage": {},
        "latency_ms": [],
        "updated_at": None,
    }


def _load_dashboard_store():
    if not RUNTIME_DASHBOARD_FILE.exists():
        return _default_dashboard_store()

    try:
        payload = json.loads(RUNTIME_DASHBOARD_FILE.read_text(encoding="utf-8"))
    except Exception:
        return _default_dashboard_store()

    base = _default_dashboard_store()
    base.update(payload)
    migrated_requests = []
    for event in payload.get("request_log", []):
        migrated = dict(event)
        migrated.pop("question_preview", None)
        migrated["dispute_label"] = migrated.get("dispute_label") or "Legacy request"
        migrated_requests.append(migrated)
    base["request_log"] = migrated_requests
    base["login_events"] = payload.get("login_events", [])
    base["token_totals"].update(payload.get("token_totals", {}))
    base["model_usage"] = payload.get("model_usage", {})
    base["mode_usage"] = payload.get("mode_usage", {})
    base["dispute_usage"] = payload.get("dispute_usage", {})
    base["latency_ms"] = payload.get("latency_ms", [])
    return base


dashboard_store = _load_dashboard_store()


def _save_dashboard_store():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DASHBOARD_FILE.write_text(
        json.dumps(dashboard_store, indent=2),
        encoding="utf-8",
    )


def _coerce_int(value) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _estimate_tokens(text: str) -> int:
    compact = (text or "").strip()
    if not compact:
        return 0
    return max(1, len(compact) // 4)


def _extract_usage(response, prompt_text: str, answer_text: str):
    usage = getattr(response, "usage", None)
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0

    if usage:
        prompt_tokens = _coerce_int(
            getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", None)
        )
        completion_tokens = _coerce_int(
            getattr(usage, "output_tokens", None) or getattr(usage, "completion_tokens", None)
        )
        total_tokens = _coerce_int(getattr(usage, "total_tokens", None))

    if not prompt_tokens:
        prompt_tokens = _estimate_tokens(prompt_text)
    if not completion_tokens:
        completion_tokens = _estimate_tokens(answer_text)
    if not total_tokens:
        total_tokens = prompt_tokens + completion_tokens

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _record_request_event(dispute_label: str, mode: str, latency_ms: float, token_usage: dict, status_label: str):
    event = {
        "timestamp": datetime.now().isoformat(),
        "dispute_label": dispute_label,
        "mode": mode,
        "latency_ms": round(latency_ms, 2),
        "prompt_tokens": token_usage["prompt_tokens"],
        "completion_tokens": token_usage["completion_tokens"],
        "total_tokens": token_usage["total_tokens"],
        "status": status_label,
        "model": GROQ_MODEL if token_usage["total_tokens"] else "vectorstore-only",
    }

    dashboard_store["request_log"].append(event)
    dashboard_store["request_log"] = dashboard_store["request_log"][-200:]

    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        dashboard_store["token_totals"][key] = (
            _coerce_int(dashboard_store["token_totals"].get(key))
            + token_usage[key]
        )

    dashboard_store["latency_ms"].append(round(latency_ms, 2))
    dashboard_store["latency_ms"] = dashboard_store["latency_ms"][-200:]

    model_usage = Counter(dashboard_store.get("model_usage", {}))
    model_usage[event["model"]] += 1
    dashboard_store["model_usage"] = dict(model_usage)

    mode_usage = Counter(dashboard_store.get("mode_usage", {}))
    mode_usage[mode] += 1
    dashboard_store["mode_usage"] = dict(mode_usage)

    dispute_usage = Counter(dashboard_store.get("dispute_usage", {}))
    dispute_usage[dispute_label] += 1
    dashboard_store["dispute_usage"] = dict(dispute_usage)
    dashboard_store["updated_at"] = event["timestamp"]
    _save_dashboard_store()


def _record_login_event(user_id: str, role: str):
    event = {
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id,
        "role": role,
    }
    dashboard_store["login_events"].append(event)
    dashboard_store["login_events"] = dashboard_store["login_events"][-200:]
    runtime_metrics["logins"] += 1
    if role == "admin":
        runtime_metrics["admin_logins"] += 1
    else:
        runtime_metrics["user_logins"] += 1
    dashboard_store["updated_at"] = event["timestamp"]
    _save_dashboard_store()


def _latest_benchmark_report():
    reports = sorted(
        MODEL_REPORTS_DIR.glob("metrics_report_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        return None

    try:
        payload = json.loads(reports[0].read_text(encoding="utf-8"))
    except Exception:
        return None

    return {
        "path": str(reports[0]),
        "generated_at": payload.get("generated_at"),
        "summary": payload.get("summary", {}),
    }


def _hourly_request_series():
    now = datetime.now()
    series = []
    events = dashboard_store.get("request_log", [])
    for offset in range(23, -1, -1):
        start = now - timedelta(hours=offset)
        bucket_label = start.strftime("%H:%M")
        bucket_key = start.strftime("%Y-%m-%d %H")
        count = 0
        for event in events:
            stamp = event.get("timestamp")
            if not stamp:
                continue
            try:
                event_dt = datetime.fromisoformat(stamp)
            except ValueError:
                continue
            if event_dt.strftime("%Y-%m-%d %H") == bucket_key:
                count += 1
        series.append({"label": bucket_label, "value": count})
    return series


def _token_series():
    events = dashboard_store.get("request_log", [])[-20:]
    series = []
    for index, event in enumerate(events, start=1):
        series.append(
            {
                "label": str(index),
                "value": _coerce_int(event.get("total_tokens")),
            }
        )
    return series


def _dashboard_payload():
    latest_report = _latest_benchmark_report()
    latency_values = [_coerce_int(value) for value in dashboard_store.get("latency_ms", []) if value is not None]
    recent_requests = dashboard_store.get("request_log", [])[-10:]
    recent_logins = dashboard_store.get("login_events", [])[-10:]
    top_acts = sorted(
        (
            {"label": key.replace("act:", ""), "value": value}
            for key, value in runtime_metrics.items()
            if key.startswith("act:")
        ),
        key=lambda item: item["value"],
        reverse=True,
    )[:5]
    benchmark_metrics = []
    if latest_report and latest_report.get("summary"):
        benchmark_metrics = [
            {"label": key.replace("_", " "), "value": value}
            for key, value in latest_report["summary"].items()
            if key != "cases"
        ]
    dispute_analytics = sorted(
        (
            {"label": label, "value": value}
            for label, value in dashboard_store.get("dispute_usage", {}).items()
        ),
        key=lambda item: item["value"],
        reverse=True,
    )

    return {
        "overview": {
            "queries": runtime_metrics.get("queries", 0),
            "logins": runtime_metrics.get("logins", 0),
            "rag_answers": runtime_metrics.get("rag_answers", 0),
            "fallback_answers": runtime_metrics.get("llm_fallback_answers", 0)
            + runtime_metrics.get("vector_only_fallback_answers", 0),
            "errors": runtime_metrics.get("llm_errors", 0),
            "avg_latency_ms": round(sum(latency_values) / len(latency_values), 2) if latency_values else 0.0,
            "vectorstore_loaded": bool(db),
        },
        "token_totals": dashboard_store.get("token_totals", {}),
        "runtime_metrics": dict(runtime_metrics),
        "mode_usage": dashboard_store.get("mode_usage", {}),
        "model_usage": dashboard_store.get("model_usage", {}),
        "dispute_usage": dashboard_store.get("dispute_usage", {}),
        "dispute_analytics": dispute_analytics,
        "top_acts": top_acts,
        "traffic_series": _hourly_request_series(),
        "token_series": _token_series(),
        "recent_requests": recent_requests,
        "recent_logins": recent_logins,
        "latest_benchmark": latest_report,
        "benchmark_metrics": benchmark_metrics,
        "updated_at": dashboard_store.get("updated_at"),
    }


def _admin_auth(credentials: HTTPBasicCredentials = Depends(security)):
    valid_user = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    valid_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (valid_user and valid_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def _response_text(response) -> str:
    return str(getattr(response, "output_text", None) or getattr(response, "output", "") or "").strip()


def _filter_results_by_score(question: str, results_with_scores):
    query_terms = {
        term for term in re.findall(r"[a-zA-Z0-9]+", question.lower())
        if len(term) > 3
    }

    rescored = []
    for doc, score in results_with_scores:
        if score < MIN_RELEVANCE_SCORE:
            continue
        doc_terms = set(re.findall(r"[a-zA-Z0-9]+", doc.page_content.lower()))
        overlap_bonus = len(query_terms & doc_terms) * 0.02
        rescored.append((doc, score + overlap_bonus))

    rescored.sort(key=lambda item: item[1], reverse=True)
    return rescored[:RETRIEVAL_RETURN_K]


def _build_search_query(question: str, analysis: QuestionAnalysis) -> str:
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


def _search(question: str, analysis: QuestionAnalysis):
    if not db:
        return []

    search_query = _build_search_query(question, analysis)
    filter_fn = None
    if analysis.applicable_acts:
        applicable = set(analysis.applicable_acts)
        filter_fn = lambda doc: doc.metadata.get("act_name") in applicable

    try:
        scoped = db.similarity_search_with_score(
            search_query,
            k=RETRIEVAL_K,
            filter=filter_fn,
        )
    except TypeError:
        scoped = db.similarity_search_with_score(search_query, k=RETRIEVAL_K)
        if filter_fn:
            scoped = [(doc, score) for doc, score in scoped if filter_fn(doc)]

    filtered = _filter_results_by_score(question, scoped)
    if filtered or not analysis.applicable_acts:
        return filtered

    fallback = db.similarity_search_with_score(search_query, k=RETRIEVAL_K)
    return _filter_results_by_score(question, fallback)


def _build_context(results_with_scores):
    context_blocks = []
    for index, (doc, score) in enumerate(results_with_scores, start=1):
        label = format_source_label(doc.metadata)
        context_blocks.append(
            f"[Source {index} | score={score:.3f} | {label}]\n{doc.page_content}"
        )
    return "\n\n".join(context_blocks)


def _vectorstore_only_answer(question: str, analysis: QuestionAnalysis, results_with_scores):
    guidance = build_procedural_guidance(analysis)
    if not results_with_scores:
        return (
            "No sufficiently relevant statutory context was retrieved.\n\n"
            f"Likely dispute type: {guidance['label']}.\n"
            f"Suggested authority or forum to check first: {guidance['suggested_authority']}\n"
            f"Suggested type of lawyer: {guidance['suggested_lawyer_type']}\n"
            f"Safety notice: {guidance['safety_notice']}"
        )

    top_points = []
    for doc, score in results_with_scores[:3]:
        label = format_source_label(doc.metadata)
        excerpt = doc.page_content.strip().replace("\n", " ")
        top_points.append(f"- {label} [score {score:.2f}]: {excerpt[:260]}")

    procedure_lines = "\n".join(f"- {step}" for step in guidance["procedure_steps"][:3])
    document_lines = "\n".join(f"- {item}" for item in guidance["required_documents"][:4])

    return (
        "Groq is unavailable, so this response is assembled directly from the retrieved statutory text.\n\n"
        f"Likely dispute type: {guidance['label']}\n\n"
        "Relevant statutory extracts:\n"
        + "\n".join(top_points)
        + "\n\nProcedure guidance:\n"
        + procedure_lines
        + "\n\nSuggested next steps:\n"
        + f"- Suggested forum: {guidance['suggested_forum']}\n"
        + f"- Suggested authority to approach first: {guidance['suggested_authority']}\n"
        + f"- Suggested lawyer type: {guidance['suggested_lawyer_type']}\n"
        + "\n\nDocuments to check:\n"
        + document_lines
        + f"\n\nSafety notice: {guidance['safety_notice']}"
    )


def _fallback_answer(question: str):
    return client.responses.create(
        model=GROQ_MODEL,
        input=[{"role": "user", "content": question}],
    )


def _record_source_metrics(results_with_scores):
    for doc, _ in results_with_scores:
        act_name = doc.metadata.get("act_name")
        if act_name:
            runtime_metrics[f"act:{act_name}"] += 1


@app.get("/")
def home():
    return {
        "message": "TerraLaw BD API is running. Use /ask?question=YOUR_QUESTION",
        "available_acts": sorted({meta["act_name"] for meta in ACT_CATALOG.values()}),
    }


@app.get("/metrics")
def metrics():
    return {
        "runtime_metrics": dict(runtime_metrics),
        "vectorstore_loaded": bool(db),
    }


@app.get("/track-login")
def track_login(user_id: str, role: str = "user"):
    clean_user = re.sub(r"[^a-zA-Z0-9_.@-]+", "", user_id)[:64] or "unknown"
    clean_role = "admin" if role == "admin" else "user"
    _record_login_event(clean_user, clean_role)
    return {"status": "ok"}


@app.get("/admin/api/dashboard")
def admin_dashboard_data(_admin: str = Depends(_admin_auth)):
    return _dashboard_payload()


@app.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(_admin: str = Depends(_admin_auth)):
    return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>TerraLaw BD Admin Dashboard</title>
  <style>
    :root {
      --bg: #eef4ef;
      --panel: #fbfdfb;
      --line: #d8e1da;
      --text: #152320;
      --muted: #697873;
      --accent: #1f6f5f;
      --accent-soft: #dff0e8;
      --warn: #a83d2f;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", sans-serif;
      background: linear-gradient(180deg, #edf5ef 0%, #f8fbf9 100%);
      color: var(--text);
    }
    .wrap {
      max-width: 1280px;
      margin: 0 auto;
      padding: 24px;
    }
    .hero, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: 0 10px 30px rgba(31, 111, 95, 0.06);
    }
    .hero {
      padding: 24px 28px;
      margin-bottom: 18px;
    }
    .hero h1 {
      margin: 0 0 8px;
      font-size: 28px;
    }
    .hero p {
      margin: 0;
      color: var(--muted);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 18px;
    }
    .card {
      padding: 18px;
      min-height: 120px;
    }
    .span-3 { grid-column: span 3; }
    .span-4 { grid-column: span 4; }
    .span-5 { grid-column: span 5; }
    .span-6 { grid-column: span 6; }
    .span-7 { grid-column: span 7; }
    .span-8 { grid-column: span 8; }
    .span-12 { grid-column: span 12; }
    .eyebrow {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      margin-bottom: 10px;
    }
    .big {
      font-size: 34px;
      font-weight: 700;
      line-height: 1;
      margin-bottom: 6px;
    }
    .sub {
      color: var(--muted);
      font-size: 13px;
    }
    .chart {
      display: flex;
      align-items: end;
      gap: 8px;
      height: 220px;
      padding-top: 16px;
    }
    .bar-wrap {
      flex: 1;
      min-width: 0;
      text-align: center;
    }
    .bar {
      width: 100%;
      border-radius: 12px 12px 4px 4px;
      background: linear-gradient(180deg, #2a8774 0%, #1f6f5f 100%);
      min-height: 3px;
    }
    .bar-label {
      margin-top: 8px;
      font-size: 11px;
      color: var(--muted);
    }
    .metric-list {
      display: grid;
      gap: 12px;
    }
    .metric-row {
      display: grid;
      grid-template-columns: 180px 1fr 52px;
      gap: 12px;
      align-items: center;
    }
    .metric-bar {
      height: 10px;
      border-radius: 999px;
      background: #ebf1ed;
      overflow: hidden;
    }
    .metric-bar > span {
      display: block;
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, #6bc694 0%, #1f6f5f 100%);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }
    th, td {
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid #e8efea;
      vertical-align: top;
    }
    th {
      color: var(--muted);
      font-weight: 600;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }
    .pill {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 12px;
      font-weight: 600;
    }
    .warning { color: var(--warn); }
    @media (max-width: 1080px) {
      .span-3, .span-4, .span-5, .span-6, .span-7, .span-8 { grid-column: span 12; }
      .metric-row { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>TerraLaw BD Admin Dashboard</h1>
      <p>Live runtime usage, token consumption, traffic load, and latest benchmark metrics.</p>
    </section>
    <section class="grid">
      <div class="panel card span-3"><div class="eyebrow">Total Queries</div><div class="big" id="queries">0</div><div class="sub">Requests processed by the API</div></div>
      <div class="panel card span-3"><div class="eyebrow">Total Tokens</div><div class="big" id="totalTokens">0</div><div class="sub">Prompt + completion tokens</div></div>
      <div class="panel card span-3"><div class="eyebrow">Avg Latency</div><div class="big" id="latency">0 ms</div><div class="sub">Average request time</div></div>
      <div class="panel card span-3"><div class="eyebrow">User Logins</div><div class="big" id="logins">0</div><div class="sub">Successful chat and admin sign-ins</div></div>

      <div class="panel card span-7">
        <div class="eyebrow">Traffic Load (Last 24 Hours)</div>
        <div class="chart" id="trafficChart"></div>
      </div>
      <div class="panel card span-5">
        <div class="eyebrow">Token Usage (Last 20 Requests)</div>
        <div class="chart" id="tokenChart"></div>
      </div>

      <div class="panel card span-6">
        <div class="eyebrow">Latest Benchmark Metrics</div>
        <div class="metric-list" id="benchmarkList"></div>
      </div>
      <div class="panel card span-6">
        <div class="eyebrow">Runtime Distribution</div>
        <div class="metric-list" id="modeList"></div>
        <div style="height:16px"></div>
        <div class="eyebrow">Top Acts Queried</div>
        <div class="metric-list" id="actList"></div>
      </div>

      <div class="panel card span-12">
        <div class="eyebrow">Dispute Type Analytics</div>
        <div class="sub">Private admin summary of which dispute categories users ask most often</div>
        <div style="height:16px"></div>
        <div class="metric-list" id="disputeList"></div>
      </div>

      <div class="panel card span-12">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:16px">
          <div>
            <div class="eyebrow">Recent Requests</div>
            <div class="sub">Private admin activity log without exposing full user question text</div>
          </div>
          <div class="pill" id="updatedAt">Updated just now</div>
        </div>
        <div style="overflow:auto; margin-top: 14px;">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Mode</th>
                <th>Dispute Type</th>
                <th>Latency</th>
                <th>Tokens</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody id="recentRequests"></tbody>
          </table>
        </div>
      </div>

      <div class="panel card span-12">
        <div class="eyebrow">Recent Logins</div>
        <div style="overflow:auto; margin-top: 14px;">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Role</th>
                <th>User ID</th>
              </tr>
            </thead>
            <tbody id="recentLogins"></tbody>
          </table>
        </div>
      </div>
    </section>
  </div>
  <script>
    function fmt(value) {
      return new Intl.NumberFormat().format(value || 0);
    }

    function renderBars(targetId, series) {
      const target = document.getElementById(targetId);
      target.innerHTML = "";
      const max = Math.max(...series.map(item => item.value), 1);
      series.forEach(item => {
        const wrap = document.createElement("div");
        wrap.className = "bar-wrap";
        const bar = document.createElement("div");
        bar.className = "bar";
        bar.style.height = `${Math.max((item.value / max) * 180, item.value ? 8 : 3)}px`;
        bar.title = `${item.label}: ${item.value}`;
        const label = document.createElement("div");
        label.className = "bar-label";
        label.textContent = item.label;
        wrap.appendChild(bar);
        wrap.appendChild(label);
        target.appendChild(wrap);
      });
    }

    function renderMetricList(targetId, items, asPercent) {
      const target = document.getElementById(targetId);
      target.innerHTML = "";
      items.forEach(item => {
        const row = document.createElement("div");
        row.className = "metric-row";
        const label = document.createElement("div");
        label.textContent = item.label;
        const barOuter = document.createElement("div");
        barOuter.className = "metric-bar";
        const barInner = document.createElement("span");
        const pct = asPercent ? Math.round((item.value || 0) * 100) : Math.min(item.value || 0, 100);
        barInner.style.width = `${pct}%`;
        barOuter.appendChild(barInner);
        const value = document.createElement("div");
        value.textContent = asPercent ? `${pct}%` : fmt(item.value);
        row.appendChild(label);
        row.appendChild(barOuter);
        row.appendChild(value);
        target.appendChild(row);
      });
    }

    function renderRecentRequests(rows) {
      const target = document.getElementById("recentRequests");
      target.innerHTML = "";
      rows.slice().reverse().forEach(item => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${new Date(item.timestamp).toLocaleString()}</td>
          <td><span class="pill">${item.mode}</span></td>
          <td>${item.dispute_label || "Unknown"}</td>
          <td>${item.latency_ms} ms</td>
          <td>${fmt(item.total_tokens)}</td>
          <td>${item.status}</td>
        `;
        target.appendChild(tr);
      });
    }

    function renderRecentLogins(rows) {
      const target = document.getElementById("recentLogins");
      target.innerHTML = "";
      rows.slice().reverse().forEach(item => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${new Date(item.timestamp).toLocaleString()}</td>
          <td><span class="pill">${item.role}</span></td>
          <td>${item.user_id}</td>
        `;
        target.appendChild(tr);
      });
    }

    async function boot() {
      const response = await fetch("/admin/api/dashboard", { cache: "no-store" });
      const data = await response.json();

      document.getElementById("queries").textContent = fmt(data.overview.queries);
      document.getElementById("totalTokens").textContent = fmt(data.token_totals.total_tokens);
      document.getElementById("latency").textContent = `${data.overview.avg_latency_ms} ms`;
      document.getElementById("logins").textContent = fmt(data.overview.logins);
      document.getElementById("updatedAt").textContent = data.updated_at ? `Updated ${new Date(data.updated_at).toLocaleString()}` : "No runtime updates yet";

      renderBars("trafficChart", data.traffic_series);
      renderBars("tokenChart", data.token_series);

      renderMetricList("benchmarkList", data.benchmark_metrics || [], true);

      const modeItems = Object.entries(data.mode_usage || {}).map(([label, value]) => ({ label, value }));
      renderMetricList("modeList", modeItems, false);
      renderMetricList("actList", data.top_acts || [], false);
      renderMetricList("disputeList", data.dispute_analytics || [], false);
      renderRecentRequests(data.recent_requests || []);
      renderRecentLogins(data.recent_logins || []);
    }

    boot();
    setInterval(boot, 5000);
  </script>
</body>
</html>
"""


@app.get("/ask")
def ask(question: str):
    started_at = datetime.now()
    runtime_metrics["queries"] += 1
    analysis = analyze_question(question)
    guidance = build_procedural_guidance(analysis)

    if not db:
        runtime_metrics["vectorstore_unavailable"] += 1
        try:
            response = _fallback_answer(question)
            answer = _response_text(response)
            token_usage = _extract_usage(response, question, answer)
            runtime_metrics["llm_only_answers"] += 1
            _record_request_event(
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
            _record_request_event(
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

    results_with_scores = _search(question, analysis)
    _record_source_metrics(results_with_scores)
    sources_used = summarize_sources(results_with_scores)

    if not results_with_scores:
        runtime_metrics["low_relevance_queries"] += 1
        try:
            response = _fallback_answer(question)
            answer = _response_text(response)
            token_usage = _extract_usage(response, question, answer)
            runtime_metrics["llm_fallback_answers"] += 1
            _record_request_event(
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
            _record_request_event(
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

    context = _build_context(results_with_scores)
    prompt = f"""
You are TerraLaw BD, an informational legal assistant for Bangladeshi land law.

Your job is to answer in clear, natural, plain English that sounds like a helpful human explanation, not a rigid legal form.

Safety rules:
- Do not present yourself as a lawyer.
- Do not invent facts, procedures, deadlines, or citations.
- Use only the retrieved legal context for statute-grounded conclusions.
- If the context is insufficient, say so plainly.

Writing style:
- Paraphrase the legal material into simple, natural language.
- Avoid sounding robotic, repetitive, or overly formal.
- Do not use the same fixed headings in every answer.
- Do not format the answer with labels such as "Issue", "Short Answer", "Applicable Law", "Procedure", "Suggested Next Steps", "Documents", "Citation", or "Safety Notice".
- Start with a direct answer in 1 or 2 short paragraphs.
- Use short bullets only when they genuinely help, such as for steps or documents.
- If the user asks a narrow question, keep the answer tight.
- If the user asks a practical question, include practical next steps in natural wording.

Content requirements:
- Briefly explain the likely legal position based on the retrieved text.
- Mention the most relevant Act and section number(s) only if they are visible in the context.
- If useful, mention:
  - likely next step
  - likely forum or authority
  - likely type of lawyer
  - key documents
- Include a short safety note at the end saying the response is informational and not a substitute for a licensed legal professional.

Dispute analysis:
- Dispute type: {guidance['label']}
- Confidence: {guidance['confidence']}
- Likely applicable acts: {', '.join(guidance['applicable_acts']) or 'Use the retrieved sources only'}
- Matched keywords: {', '.join(guidance['matched_keywords']) or 'None'}

Routing hints for this dispute:
- Suggested forum: {guidance['suggested_forum']}
- Suggested authority: {guidance['suggested_authority']}
- Suggested lawyer type: {guidance['suggested_lawyer_type']}

Retrieved legal context:
{context}

User question:
{question}
"""

    try:
        response = client.responses.create(
            model=GROQ_MODEL,
            input=[{"role": "user", "content": prompt}],
        )
        answer = _response_text(response)
        token_usage = _extract_usage(response, prompt, answer)
        runtime_metrics["rag_answers"] += 1
        mode = "rag"
        status_label = "ok"
    except openai.PermissionDeniedError:
        runtime_metrics["vector_only_fallback_answers"] += 1
        answer = _vectorstore_only_answer(question, analysis, results_with_scores)
        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        mode = "vector_only"
        status_label = "permission_denied"
    except Exception as exc:
        runtime_metrics["llm_errors"] += 1
        answer = (
            "The language model request failed, so the system is returning grounded statutory guidance only.\n\n"
            + _vectorstore_only_answer(question, analysis, results_with_scores)
            + f"\n\nSystem note: {exc}"
        )
        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        mode = "vector_only"
        status_label = "llm_error"

    if answer and "information not found" in answer.lower():
        runtime_metrics["insufficient_context_answers"] += 1

    _record_request_event(
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
