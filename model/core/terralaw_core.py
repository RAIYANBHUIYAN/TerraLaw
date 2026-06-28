import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


ACT_CATALOG: dict[str, dict[str, Any]] = {
    "TPA_1882_cleaned.txt": {
        "act_name": "Transfer of Property Act",
        "act_year": "1882",
        "aliases": ["transfer of property act", "tpa"],
        "default_tags": ["sale_transfer", "ownership_title", "mortgage_gift_lease"],
    },
    "SAT_1950_cleaned.txt": {
        "act_name": "State Acquisition and Tenancy Act",
        "act_year": "1950",
        "aliases": ["state acquisition and tenancy act", "sat"],
        "default_tags": ["tenancy_rent", "record_of_rights", "landholding", "preemption"],
    },
    "NAT_1949_cleaned.txt": {
        "act_name": "Non-Agricultural Tenancy Act",
        "act_year": "1949",
        "aliases": ["non-agricultural tenancy act", "nat"],
        "default_tags": ["tenancy_rent", "non_agricultural_tenancy"],
    },
    "ARIPA_2017_cleaned.txt": {
        "act_name": "Acquisition and Requisition of Immovable Property Act",
        "act_year": "2017",
        "aliases": [
            "acquisition and requisition of immovable property act",
            "aripa",
            "acquisition and requisition",
        ],
        "default_tags": ["land_acquisition", "compensation"],
    },
    "Land_Tax_2023_cleaned.txt": {
        "act_name": "Land Development Tax Act",
        "act_year": "2023",
        "aliases": ["land development tax act", "land tax", "land development tax"],
        "default_tags": ["land_tax"],
    },
}


DISPUTE_PLAYBOOK: dict[str, dict[str, Any]] = {
    "sale_transfer": {
        "label": "Sale and transfer of immovable property",
        "keywords": ["sale", "sell", "transfer", "ownership", "title deed", "registration", "buyer", "seller"],
        "applicable_acts": ["Transfer of Property Act"],
        "procedures": [
            "Identify the land, parties, and nature of transfer before applying any statutory rule.",
            "Confirm whether the transaction is sale, gift, mortgage, lease, exchange, or another transfer category.",
            "Check the statutory definition, formal requirements, and any registration or affidavit requirement visible in the retrieved sections.",
            "Match the facts to the section-specific rule and note any limitation, condition, or exception stated in the statute.",
        ],
        "documents": [
            "Title deed or prior transfer deed",
            "Khatiyan / record-of-rights extract",
            "Mutation record, if relevant",
            "Land tax receipt",
            "Registration-related papers and identity documents",
        ],
        "safety_notes": [
            "A chatbot cannot verify title defects or forged documents.",
            "Where competing title claims exist, a licensed lawyer and land records verification are necessary.",
        ],
        "suggested_forum": "Usually a civil court or land-related civil forum, with land office records checked in parallel.",
        "suggested_authority": "Sub-Registrar office for deed and registration records, plus local land office for khatiyan and mutation records.",
        "lawyer_type": "A civil lawyer experienced in property, title, and land transfer matters.",
    },
    "tenancy_rent": {
        "label": "Tenancy, rent, and possession disputes",
        "keywords": ["tenant", "tenancy", "rent", "raiyat", "under-raiyat", "eviction", "lease", "possession"],
        "applicable_acts": ["State Acquisition and Tenancy Act", "Non-Agricultural Tenancy Act"],
        "procedures": [
            "Identify whether the land use is agricultural or non-agricultural.",
            "Determine the tenancy category and the statutory rights or liabilities attached to that category.",
            "Check the relevant provisions on rent, possession, eviction, transferability, or subletting.",
            "List the factual documents needed to prove possession, rent status, and the tenant-landlord relationship.",
        ],
        "documents": [
            "Rent receipts",
            "Lease deed or tenancy agreement",
            "Record-of-rights / khatiyan",
            "Mutation papers",
            "Possession-related evidence such as utility bills or tax receipts",
        ],
        "safety_notes": [
            "Tenancy disputes often turn on possession evidence and local revenue records.",
            "Eviction or recovery strategy should be checked with a lawyer before action is taken.",
        ],
        "suggested_forum": "Usually a civil or tenancy-related forum, depending on the tenancy category and relief sought.",
        "suggested_authority": "Local land office or revenue office for tenancy and possession records before filing any formal case.",
        "lawyer_type": "A civil lawyer familiar with tenancy, possession, and land record disputes.",
    },
    "record_of_rights": {
        "label": "Record-of-rights, survey, and land record disputes",
        "keywords": ["record of rights", "khatiyan", "survey", "mutation", "record", "cs", "sa", "rs", "porcha"],
        "applicable_acts": ["State Acquisition and Tenancy Act"],
        "procedures": [
            "Identify which survey or record stage is in dispute.",
            "Check the statutory provision on preparation, correction, or maintenance of the record-of-rights.",
            "Distinguish between administrative correction issues and substantive title disputes.",
            "Collect documentary proof that links possession, title, and the disputed entry.",
        ],
        "documents": [
            "Khatiyan / porcha copies",
            "Mutation order",
            "Title deeds",
            "Survey maps or field book extracts",
            "Tax receipts",
        ],
        "safety_notes": [
            "A record entry may support a claim but does not always settle title conclusively.",
        ],
        "suggested_forum": "Often starts before land record or revenue authorities; title disputes may later require a civil court.",
        "suggested_authority": "Assistant Commissioner (Land), Union Land Office, or the relevant survey/record correction authority.",
        "lawyer_type": "A land or revenue lawyer who also handles civil title disputes.",
    },
    "land_acquisition": {
        "label": "Land acquisition, requisition, and compensation",
        "keywords": [
            "acquisition",
            "requisition",
            "compensation",
            "award",
            "public purpose",
            "deputy commissioner",
            "object",
            "objection",
            "objecting",
            "notice",
            "arbitrator",
        ],
        "applicable_acts": ["Acquisition and Requisition of Immovable Property Act"],
        "procedures": [
            "Identify whether the issue concerns notice, objection, award, compensation, possession, or appeal/arbitration.",
            "Check the statutory timeline and authority responsible at the current stage.",
            "Extract the compensation rule, objection window, or appeal mechanism directly from the cited provisions.",
            "List the ownership and valuation documents required to support the claim.",
        ],
        "documents": [
            "Acquisition notice",
            "Ownership deed",
            "Khatiyan / record-of-rights",
            "Valuation or compensation papers",
            "Any objection, award, or arbitration documents",
        ],
        "safety_notes": [
            "Limitation periods in acquisition matters can be short and should be checked immediately.",
        ],
        "suggested_forum": "Usually begins before the acquisition authority and may move to arbitration or court depending on the statutory remedy.",
        "suggested_authority": "Deputy Commissioner or the acquisition authority handling the notice, objection, award, or compensation stage.",
        "lawyer_type": "A land acquisition or administrative lawyer; for compensation disputes, a civil lawyer with acquisition experience is usually suitable.",
    },
    "land_tax": {
        "label": "Land development tax and revenue issues",
        "keywords": ["land tax", "development tax", "tax", "revenue", "assessment", "exemption"],
        "applicable_acts": ["Land Development Tax Act"],
        "procedures": [
            "Identify the land type and whether it is agricultural or non-agricultural.",
            "Check the rate, exemption, assessment, and appeal rules in the relevant statutory provisions.",
            "Confirm whether any special schedule or exemption category applies.",
            "Gather ownership and holding-size records before calculating liability.",
        ],
        "documents": [
            "Land tax receipt",
            "Khatiyan / holding record",
            "Mutation papers",
            "Assessment order or demand notice",
        ],
        "safety_notes": [
            "Tax classification disputes may depend on factual land use and official schedules.",
        ],
        "suggested_forum": "Usually a revenue or tax-related authority first, with court proceedings only if the statutory route requires it.",
        "suggested_authority": "The land revenue or tax assessment authority named in the demand notice or assessment record.",
        "lawyer_type": "A revenue or land tax lawyer, or a civil lawyer who handles land revenue matters.",
    },
    "preemption": {
        "label": "Pre-emption and co-sharer disputes",
        "keywords": ["pre-emption", "preemption", "co-sharer", "co owner", "co-owner", "share", "sharer"],
        "applicable_acts": ["State Acquisition and Tenancy Act", "Transfer of Property Act"],
        "procedures": [
            "Identify whether the right asserted is statutory pre-emption or a general title/transfer challenge.",
            "Check the section governing transfer and the section specifically addressing pre-emption, if retrieved.",
            "Confirm the relationship of the claimant to the land and the relevant transfer event.",
            "Collect transfer papers, record-of-rights, and evidence of co-sharer status.",
        ],
        "documents": [
            "Sale deed",
            "Khatiyan / co-sharer record",
            "Mutation papers",
            "Notice or knowledge of transfer evidence",
        ],
        "safety_notes": [
            "Pre-emption is highly fact-sensitive and limitation-driven.",
        ],
        "suggested_forum": "Usually a civil court or the statutory forum dealing with pre-emption claims, depending on the governing provision.",
        "suggested_authority": "Collect the sale deed, mutation, and co-sharer records from the Sub-Registrar office and land records office before filing.",
        "lawyer_type": "A civil lawyer experienced in land, co-sharer, and pre-emption litigation.",
    },
    "general_land_law": {
        "label": "General land law query",
        "keywords": [],
        "applicable_acts": [],
        "procedures": [
            "Clarify the land issue, relevant statute, and stage of dispute.",
            "Use the retrieved statutory sections as the primary basis of explanation.",
        ],
        "documents": [
            "Title deed",
            "Khatiyan / record-of-rights",
            "Mutation papers",
            "Tax receipts",
        ],
        "safety_notes": [
            "This system is informational and does not replace a licensed legal professional.",
        ],
        "suggested_forum": "The correct forum depends on whether the issue is title, possession, records, tax, or acquisition.",
        "suggested_authority": "Start by checking the relevant land office, registration office, or notice-issuing authority tied to the dispute.",
        "lawyer_type": "A civil or land lawyer who can review the facts and documents in detail.",
    },
}


CHUNK_SIZE = 1100
CHUNK_OVERLAP = 150
MAX_WHOLE_SECTION_CHARS = 1100

CHUNK_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=[
        "\n\n",
        r"\n\([a-z]+\)\s",
        r"\n\(\d+\)\s",
        "\n",
        "; ",
        ". ",
        " ",
    ],
    is_separator_regex=True,
)


@dataclass
class QuestionAnalysis:
    dispute_type: str
    label: str
    confidence: float
    matched_keywords: list[str]
    applicable_acts: list[str]
    procedures: list[str]
    documents: list[str]
    safety_notes: list[str]


def clean_legal_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\ufeff", "")
    text = text.replace("\xa0", " ")
    text = text.replace("â€”", "-").replace("â€“", "-")
    text = text.replace("â€œ", '"').replace("â€", '"')
    text = text.replace("â€™", "'").replace("â€˜", "'")
    text = re.sub(r"(?<!\n)(?=\bPART\s+[A-Z0-9]+\b)", "\n", text)
    text = re.sub(r"(?<!\n)(?=\bCHAPTER\s+[A-Z0-9]+\b)", "\n", text)
    text = re.sub(r"(?<=[A-Za-z\]\)])\s+(?=\d+[A-Z]?\.\s)", "\n", text)
    text = re.sub(r"(?<=[.;:])\s+(?=\([a-z]+\))", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_act_metadata(source_name: str, text: str) -> dict[str, Any]:
    source_meta = ACT_CATALOG.get(source_name, {})
    header = text[:1200]

    act_name = source_meta.get("act_name")
    if not act_name:
        name_match = re.search(r"THE\s+([A-Z ,'-]+?(?:ACT|ORDINANCE))", header, re.IGNORECASE)
        act_name = name_match.group(1).title() if name_match else source_name.replace("_cleaned.txt", "")

    year = source_meta.get("act_year")
    if not year:
        year_match = re.search(r"\b(18|19|20)\d{2}\b", header)
        year = year_match.group(0) if year_match else ""

    act_number_match = re.search(
        r"(?:(?:ACT|ORDINANCE)\s+NO\.?\s*([A-Z0-9 .-]+OF\s+\d{4})|ACT\s+([A-Z0-9 .-]+OF\s+\d{4}))",
        header,
        re.IGNORECASE,
    )
    act_number = next((group for group in act_number_match.groups() if group), "") if act_number_match else ""

    return {
        "source": source_name,
        "act_name": act_name,
        "act_year": year,
        "act_number": act_number.strip(" ."),
        "default_tags": source_meta.get("default_tags", []),
    }


def _looks_like_heading(line: str) -> bool:
    compact = line.strip()
    if not compact or len(compact) > 120:
        return False
    if compact.endswith((".", ";", ":")):
        return False
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9 ,'\-/()]+$", compact))


def parse_legal_sections(text: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    sections: list[dict[str, Any]] = []
    current_part = ""
    current_chapter = ""
    current: dict[str, Any] | None = None
    pending_heading = ""

    def flush_current() -> None:
        nonlocal current
        if current and current["content"].strip():
            sections.append(current)
        current = None

    for line in lines:
        if re.match(r"^PART\s+[A-Z0-9]+", line, re.IGNORECASE):
            current_part = line
            continue

        if re.match(r"^CHAPTER\s+[A-Z0-9]+", line, re.IGNORECASE):
            current_chapter = line
            continue

        inline_match = re.match(
            r"^(?P<title>[A-Za-z][A-Za-z0-9 ,'\-/()]+?)\s+(?P<section>\d+[A-Z]?)\.\s*(?P<body>.+)$",
            line,
        )
        section_match = re.match(r"^(?P<section>\d+[A-Z]?)\.\s*(?P<body>.*)$", line)

        if inline_match and len(inline_match.group("title")) <= 100:
            flush_current()
            current = {
                "part": current_part,
                "chapter": current_chapter,
                "section": inline_match.group("section"),
                "section_title": inline_match.group("title").strip(),
                "content": f"{inline_match.group('title').strip()} {inline_match.group('section')}. {inline_match.group('body').strip()}",
            }
            pending_heading = ""
            continue

        if section_match:
            flush_current()
            current = {
                "part": current_part,
                "chapter": current_chapter,
                "section": section_match.group("section"),
                "section_title": pending_heading,
                "content": f"{section_match.group('section')}. {section_match.group('body').strip()}",
            }
            pending_heading = ""
            continue

        if current:
            current["content"] += "\n" + line
        elif _looks_like_heading(line):
            pending_heading = line

    flush_current()
    return sections


def _section_context_prefix(act_meta: dict[str, Any], section: dict[str, Any]) -> str:
    act_label = act_meta.get("act_name", "")
    if act_meta.get("act_year"):
        act_label = f"{act_label}, {act_meta['act_year']}"

    details: list[str] = []
    section_number = section.get("section", "")
    section_title = section.get("section_title", "")
    if section_number:
        section_label = f"Section {section_number}"
        if section_title:
            section_label = f"{section_label}: {section_title}"
        details.append(section_label)
    elif section_title:
        details.append(section_title)

    chapter = section.get("chapter", "")
    if chapter:
        details.append(chapter)

    if details:
        return f"{act_label} | {' | '.join(details)}"
    return act_label


def _split_section_content(content: str) -> list[str]:
    normalized = content.strip()
    if not normalized:
        return []

    if len(normalized) <= MAX_WHOLE_SECTION_CHARS:
        return [normalized]

    return CHUNK_SPLITTER.split_text(normalized)


def build_documents_from_text(source_name: str, text: str) -> list[Document]:
    cleaned = clean_legal_text(text)
    act_meta = extract_act_metadata(source_name, cleaned)
    sections = parse_legal_sections(cleaned)
    documents: list[Document] = []

    if not sections:
        sections = [{
            "part": "",
            "chapter": "",
            "section": "",
            "section_title": "",
            "content": cleaned,
        }]

    for section_index, section in enumerate(sections):
        context_prefix = _section_context_prefix(act_meta, section)
        chunks = _split_section_content(section["content"])
        total_chunks = len(chunks)

        for chunk_index, chunk in enumerate(chunks):
            page_content = f"{context_prefix}\n\n{chunk}" if context_prefix else chunk
            metadata = {
                **act_meta,
                "part": section.get("part", ""),
                "chapter": section.get("chapter", ""),
                "section": section.get("section", ""),
                "section_title": section.get("section_title", ""),
                "section_key": f"{section.get('section', '')}:{section_index}",
                "chunk_index": chunk_index,
                "chunk_count": total_chunks,
            }
            documents.append(Document(page_content=page_content, metadata=metadata))

    return documents


def analyze_question(question: str) -> QuestionAnalysis:
    lowered = question.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", lowered)
    scores: Counter[str] = Counter()
    matched_keywords: dict[str, list[str]] = {}

    for source_meta in ACT_CATALOG.values():
        for alias in source_meta.get("aliases", []):
            normalized_alias = re.sub(r"[^a-z0-9]+", " ", alias.lower()).strip()
            if normalized_alias and normalized_alias in normalized:
                for tag in source_meta.get("default_tags", []):
                    scores[tag] += 3
                    matched_keywords.setdefault(tag, []).append(alias)

    for dispute_type, config in DISPUTE_PLAYBOOK.items():
        for keyword in config["keywords"]:
            normalized_keyword = re.sub(r"[^a-z0-9]+", " ", keyword.lower()).strip()
            if normalized_keyword and normalized_keyword in normalized:
                increment = 1
                if dispute_type in {"preemption", "land_acquisition", "land_tax"}:
                    increment = 2
                scores[dispute_type] += increment
                matched_keywords.setdefault(dispute_type, []).append(keyword)

    if not scores:
        dispute_type = "general_land_law"
        confidence = 0.25
    else:
        dispute_type, best_score = scores.most_common(1)[0]
        total = sum(scores.values())
        confidence = round(best_score / total, 2) if total else 0.25

    config = DISPUTE_PLAYBOOK[dispute_type]
    return QuestionAnalysis(
        dispute_type=dispute_type,
        label=config["label"],
        confidence=confidence,
        matched_keywords=sorted(set(matched_keywords.get(dispute_type, []))),
        applicable_acts=config["applicable_acts"],
        procedures=config["procedures"],
        documents=config["documents"],
        safety_notes=config["safety_notes"],
    )


def summarize_sources(results_with_scores: list[tuple[Document, float]]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for doc, score in results_with_scores:
        metadata = doc.metadata
        sources.append({
            "source": metadata.get("source", ""),
            "act_name": metadata.get("act_name", ""),
            "act_year": metadata.get("act_year", ""),
            "section": metadata.get("section", ""),
            "section_title": metadata.get("section_title", ""),
            "chapter": metadata.get("chapter", ""),
            "score": round(float(score), 4),
        })
    return sources


def format_source_label(metadata: dict[str, Any]) -> str:
    return format_legal_citation(metadata)


def format_legal_citation(metadata: dict[str, Any]) -> str:
    act_name = metadata.get("act_name") or metadata.get("source", "Unknown source")
    act_year = metadata.get("act_year", "")
    section = metadata.get("section")
    section_title = metadata.get("section_title")
    chapter = metadata.get("chapter")

    act_label = f"{act_name}, {act_year}" if act_year else act_name
    if section:
        section_label = f"Section {section}"
        if section_title:
            section_label = f"{section_label} ({section_title})"
        elif chapter:
            section_label = f"{section_label} — {chapter}"
        return f"{act_label} — {section_label}"
    if section_title:
        return f"{act_label} — {section_title}"
    if chapter:
        return f"{act_label} — {chapter}"
    return act_label


def build_citations_block(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return ""

    lines: list[str] = []
    seen: set[tuple[str, str]] = set()
    for source in sources:
        act_name = str(source.get("act_name", ""))
        section = str(source.get("section", ""))
        key = (act_name, section)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"• {format_legal_citation(source)}")

    if not lines:
        return ""
    return "Legal sources cited:\n" + "\n".join(lines)


def build_procedural_guidance(analysis: QuestionAnalysis) -> dict[str, Any]:
    config = DISPUTE_PLAYBOOK[analysis.dispute_type]
    return {
        "dispute_type": analysis.dispute_type,
        "label": analysis.label,
        "confidence": analysis.confidence,
        "matched_keywords": analysis.matched_keywords,
        "applicable_acts": analysis.applicable_acts,
        "procedure_steps": analysis.procedures,
        "required_documents": analysis.documents,
        "suggested_forum": config.get("suggested_forum", ""),
        "suggested_authority": config.get("suggested_authority", ""),
        "suggested_lawyer_type": config.get("lawyer_type", ""),
        "safety_notice": (
            "This response is for legal awareness only. It does not replace a licensed "
            "advocate, title verification, or official land-record checking."
        ),
        "safety_notes": analysis.safety_notes,
    }
