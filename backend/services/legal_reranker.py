"""Legal Re-Ranking Layer — Doctrinal retrieval optimization.

Transforms raw Qdrant similarity results into doctrinally curated context.

Pipeline:
  Qdrant (top 40) → Legal Filter → Diversity → Temporal → Balance → Top 12 → LLM

All processing in memory. No index reload. No vector rebuild.
"""

import logging
from typing import List, Dict
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)

CURRENT_YEAR = datetime.now().year


def rerank(
    raw_results: List[Dict],
    legal_issues: Dict = None,
    max_output: int = 12,
) -> List[Dict]:
    """Main entry: legal re-ranking of raw vector search results.

    Args:
        raw_results: Raw chunks from Qdrant (top 40)
        legal_issues: Output from Legal Issue Extractor
        max_output: Final number of chunks to return (default 12)

    Returns:
        Curated list of chunks optimized for legal reasoning
    """
    if not raw_results:
        return []

    legal_issues = legal_issues or {}

    # =========================================================
    # STEP 2: LEGAL FILTERING (score boost)
    # =========================================================
    scored = _apply_legal_filtering(raw_results, legal_issues)

    # =========================================================
    # STEP 3: DOCTRINAL DIVERSITY (group by author)
    # =========================================================
    diversified = _apply_doctrinal_diversity(scored)

    # =========================================================
    # STEP 4: TEMPORAL WEIGHT
    # =========================================================
    temporal = _apply_temporal_weight(diversified)

    # =========================================================
    # STEP 5: POSITIONAL BALANCING (majoritaria vs minoritaria)
    # =========================================================
    balanced = _apply_positional_balancing(temporal)

    # =========================================================
    # STEP 6: FINAL SELECTION (top N)
    # =========================================================
    balanced.sort(key=lambda x: x.get("final_score", 0), reverse=True)
    final = balanced[:max_output]

    # Stats
    authors = set()
    positions = set()
    for r in final:
        m = r.get("metadata", {})
        a = m.get("author_id") or m.get("author", "")
        if a:
            authors.add(a)
        p = m.get("posicao_doutrinaria", "")
        if p and p != "indefinida":
            positions.add(p)

    logger.info(
        f"Re-Rank: {len(raw_results)} raw → {len(final)} curated "
        f"({len(authors)} authors, positions: {positions or 'n/a'})"
    )

    return final


# ============================================================
# STEP 2: LEGAL FILTERING
# ============================================================

def _apply_legal_filtering(results: List[Dict], legal_issues: Dict) -> List[Dict]:
    """Boost scores based on legal relevance."""

    detected_area = (legal_issues.get("legal_area", "") or "").lower()
    detected_keywords = [k.lower() for k in legal_issues.get("keywords_for_retrieval", [])]

    # Extract article from question keywords
    question_articles = set()
    for kw in detected_keywords:
        import re
        m = re.search(r'art\.?\s*(\d+)', kw)
        if m:
            question_articles.add(m.group(1))

    for r in results:
        meta = r.get("metadata", {})
        base_score = r.get("score", 0.0)
        boost = 0.0

        # 2a: Legal subject match (+40%)
        chunk_area = (meta.get("legal_subject", "") or meta.get("materia", "") or "").lower()
        if detected_area and chunk_area and detected_area in chunk_area:
            boost += base_score * 0.40

        # 2b: Normative strength
        peso = meta.get("peso_normativo", 0)
        if isinstance(peso, str):
            try:
                peso = int(peso)
            except (ValueError, TypeError):
                peso = 0
        if peso > 1:
            boost += base_score * (peso * 0.05)  # constituicao(5)=+25%, lei(2)=+10%

        # 2c: Article reference match
        artigo = str(meta.get("artigo_referenciado", ""))
        if artigo and artigo in question_articles:
            boost += base_score * 0.20

        # 2d: Institute keyword match
        chunk_text_lower = r.get("text", "").lower()[:500]
        keyword_hits = sum(1 for kw in detected_keywords if kw in chunk_text_lower)
        if keyword_hits > 0:
            boost += base_score * min(keyword_hits * 0.05, 0.20)

        r["legal_boost"] = round(boost, 4)
        r["final_score"] = round(base_score + boost, 4)

    return results


# ============================================================
# STEP 3: DOCTRINAL DIVERSITY
# ============================================================

def _apply_doctrinal_diversity(results: List[Dict]) -> List[Dict]:
    """Ensure multiple authors, max 3 chunks per author initially."""

    # Group by author
    by_author = defaultdict(list)
    for r in results:
        meta = r.get("metadata", {})
        author_key = meta.get("author_id") or meta.get("author", "") or "unknown"
        by_author[author_key].append(r)

    # Sort each author's chunks by score
    for author in by_author:
        by_author[author].sort(key=lambda x: x.get("final_score", 0), reverse=True)

    # If 2+ authors, limit to max 3 per author initially
    # This prevents one author dominating all 12 slots
    if len(by_author) >= 2:
        diversified = []
        for author, chunks in by_author.items():
            diversified.extend(chunks[:5])  # Max 5 per author in candidate pool
        return diversified

    # Single author: return all
    all_chunks = []
    for chunks in by_author.values():
        all_chunks.extend(chunks)
    return all_chunks


# ============================================================
# STEP 4: TEMPORAL WEIGHT
# ============================================================

def _apply_temporal_weight(results: List[Dict]) -> List[Dict]:
    """Mild boost for recent doctrine. Never eliminates classics."""

    for r in results:
        meta = r.get("metadata", {})
        year = meta.get("year", meta.get("ano", 0))

        try:
            year = int(year) if year else 0
        except (ValueError, TypeError):
            year = 0

        if year > 0:
            temporal_boost = (year / CURRENT_YEAR) * 0.10
        else:
            temporal_boost = 0.0

        r["temporal_boost"] = round(temporal_boost, 4)
        r["final_score"] = round(r.get("final_score", 0) + temporal_boost, 4)

    return results


# ============================================================
# STEP 5: POSITIONAL BALANCING
# ============================================================

def _apply_positional_balancing(results: List[Dict]) -> List[Dict]:
    """Ensure doctrinal diversity: majoritaria + minoritaria/critica."""

    # Detect available positions
    by_position = defaultdict(list)
    for r in results:
        pos = r.get("metadata", {}).get("posicao_doutrinaria", "indefinida")
        by_position[pos].append(r)

    has_majority = bool(by_position.get("majoritaria"))
    has_minority = bool(by_position.get("minoritaria"))
    has_critical = bool(by_position.get("critica"))
    has_divergence = has_minority or has_critical

    if not has_divergence:
        return results

    # Ensure at least 1 majority + 1 divergent in final set
    # Give divergent views a score floor so they aren't eliminated
    if has_majority:
        top_majority = max(r.get("final_score", 0) for r in by_position["majoritaria"])
    else:
        top_majority = max(r.get("final_score", 0) for r in results) if results else 0

    # Set minimum score for divergent views (70% of top majority)
    min_divergent_score = top_majority * 0.70

    for pos_type in ["minoritaria", "critica"]:
        if pos_type in by_position:
            for r in by_position[pos_type][:2]:  # Top 2 divergent
                if r.get("final_score", 0) < min_divergent_score:
                    r["final_score"] = min_divergent_score
                    r["diversity_boosted"] = True

    logger.info(
        f"  Positional balance: majority={len(by_position.get('majoritaria', []))}, "
        f"minority={len(by_position.get('minoritaria', []))}, "
        f"critical={len(by_position.get('critica', []))}"
    )

    return results
