"""Citation Guardian v2 — Validador real de citações.

Valida se TODA citação do LLM existe nos chunks recuperados.
NÃO substitui citation_guardian.py atual. Módulo adicional.
Ativar via CITATION_GUARDIAN_V2_ENABLED=true
"""

import os
import re
import logging
from typing import List, Dict, Tuple
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

ENABLED = os.environ.get("CITATION_GUARDIAN_V2_ENABLED", "false").lower() == "true"


def _normalize(text: str) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    for k, v in {"\u00e7": "c", "\u00e3": "a", "\u00e1": "a", "\u00e2": "a", "\u00e9": "e", "\u00ea": "e", "\u00ed": "i", "\u00f3": "o", "\u00f4": "o", "\u00fa": "u"}.items():
        text = text.replace(k, v)
    return re.sub(r'\s+', ' ', text)


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio() if a and b else 0.0


def extract_all_citations(text: str) -> List[Dict]:
    """Extrai todas as cita\u00e7\u00f5es do texto gerado."""
    citations = []
    patterns = [
        r'\(([^()]+?)\.\s+([^()]+?)\.\s+(\d{4}),?\s*p\.\s*(\d+[^)]*)\)',
        r'\(([^()]+?)\.\s+([^()]+?)\.\s+(\d{4})\)',
        r'\(([^()]+?),\s+([^()]+?),\s+(\d{4}),?\s*p\.\s*(\d+[^)]*)\)',
        r'\(([^()]+?),\s+([^()]+?),\s+(\d{4})\)',
    ]
    seen = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            span = (match.start(), match.end())
            if any(s[0] <= span[0] < s[1] for s in seen):
                continue
            seen.add(span)
            groups = match.groups()
            citations.append({
                "author": groups[0].strip(),
                "title": groups[1].strip(),
                "year": int(groups[2]) if len(groups) > 2 else 0,
                "page": groups[3].strip() if len(groups) > 3 else "",
                "full_text": match.group(0),
            })
    return citations


def validate_citation_deep(citation: Dict, chunks: List[Dict]) -> Dict:
    """Valida\u00e7\u00e3o profunda: autor + obra + p\u00e1gina + compatibilidade sem\u00e2ntica."""
    cite_author = citation.get("author", "")
    cite_title = citation.get("title", "")
    cite_year = citation.get("year", 0)
    cite_page = citation.get("page", "")

    best_score = 0.0
    best_match = None
    hallucination_flags = []

    for chunk in chunks:
        meta = chunk.get("metadata", {})
        src_author = meta.get("author", "")
        src_title = meta.get("title", "")
        src_year = meta.get("year", "")
        src_page = str(meta.get("page", ""))

        try:
            src_year_int = int(src_year) if src_year else 0
        except (ValueError, TypeError):
            src_year_int = 0

        # Component scores
        author_sim = _sim(cite_author, src_author)
        title_sim = _sim(cite_title, src_title)
        year_match = 1.0 if (cite_year == src_year_int and cite_year > 0) else 0.0
        page_match = 1.0 if (cite_page and cite_page == src_page) else 0.0

        # Semantic compatibility: is citation text found in chunk?
        text_sim = 0.0
        if cite_author.lower() in chunk.get("text", "").lower():
            text_sim = 0.3

        score = (author_sim * 0.35) + (title_sim * 0.25) + (year_match * 0.15) + (page_match * 0.1) + (text_sim * 0.15)

        if score > best_score:
            best_score = score
            best_match = {
                "author": src_author, "title": src_title,
                "year": src_year_int, "page": src_page,
                "author_sim": round(author_sim, 3),
                "title_sim": round(title_sim, 3),
            }

    # Determine validation
    is_valid = best_score >= 0.40
    flag_hallucination = best_score < 0.25

    if flag_hallucination:
        hallucination_flags.append(f"Citation '{citation['full_text']}' has no matching source (score: {best_score:.2f})")

    result = {
        "citation": citation["full_text"],
        "valid": is_valid,
        "flag_hallucination": flag_hallucination,
        "confidence": round(best_score, 3),
        "best_match": best_match,
        "hallucination_flags": hallucination_flags,
    }

    if flag_hallucination:
        logger.warning(f"[GuardianV2] HALLUCINATION: {citation['full_text']} (score: {best_score:.2f})")
    elif not is_valid:
        logger.info(f"[GuardianV2] LOW CONFIDENCE: {citation['full_text']} (score: {best_score:.2f})")

    return result


def validate_response_v2(response_text: str, chunks: List[Dict]) -> Tuple[str, Dict]:
    """Valida todas as cita\u00e7\u00f5es. N\u00e3o bloqueia — apenas loga."""
    if not ENABLED:
        return response_text, {"status": "disabled"}

    citations = extract_all_citations(response_text)
    if not citations:
        return response_text, {"status": "no_citations", "total": 0}

    results = [validate_citation_deep(c, chunks) for c in citations]

    valid = sum(1 for r in results if r["valid"])
    hallucinated = sum(1 for r in results if r["flag_hallucination"])

    report = {
        "status": "validated",
        "total": len(citations),
        "valid": valid,
        "low_confidence": len(citations) - valid - hallucinated,
        "hallucinated": hallucinated,
        "details": results,
    }

    logger.info(f"[GuardianV2] {valid}/{len(citations)} valid, {hallucinated} hallucinated")
    return response_text, report
