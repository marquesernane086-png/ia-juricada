"""Doctrine Synthesizer — Stage 2 of Legal Reasoning Pipeline.

Takes grouped doctrinal contexts from Doctrine Graph Layer and produces
structured doctrinal synthesis WITHOUT answering the question.

Pipeline: Legal Analyzer → [Doctrine Synthesizer] → Legal Applicator

This stage is LOCAL PROCESSING (no LLM call) to avoid token cost.
It structures the doctrinal landscape for the final reasoning stage.
"""

from utils.logger import get_logger
from typing import List, Dict
from services.doctrine_graph import DoctrinalBlock

logger = get_logger(__name__)


# ============================================================
# DOCTRINAL POSITION SIGNALS (for position detection)
# ============================================================

POSITION_SIGNALS = {
    "majoritaria": [
        "maioria da doutrina", "entendimento dominante", "posição consolidada",
        "doutrina majoritária", "corrente majoritária", "pacífico na doutrina",
        "entendimento pacífico", "posição predominante", "majoritariamente",
        "a doutrina é unânime", "consenso doutrinário", "entendimento prevalente",
    ],
    "minoritaria": [
        "parte da doutrina", "corrente minoritária", "há quem sustente",
        "posição minoritária", "alguns autores", "isoladamente",
        "diverge parcialmente", "entendimento isolado", "minoria da doutrina",
    ],
    "critica": [
        "não concordamos", "equivoca-se", "merece crítica",
        "data venia", "com a devida vênia", "discordamos",
        "não nos parece correto", "melhor seria", "criticável",
        "inaceitável", "insustentável", "não se sustenta",
    ],
    "historica": [
        "historicamente", "direito romano", "tradicionalmente",
        "evolução histórica", "origem histórica", "no passado",
        "antiguamente", "na tradição", "desde o direito",
    ],
}


def detect_doctrinal_position(text: str) -> str:
    """Detect doctrinal position type from chunk text.

    Returns: majoritaria, minoritaria, critica, historica, conceito, or indefinida
    """
    text_lower = text.lower()

    # Count signals for each type
    scores = {}
    for position, signals in POSITION_SIGNALS.items():
        count = sum(1 for s in signals if s in text_lower)
        if count > 0:
            scores[position] = count

    if not scores:
        # Check if it's a conceptual definition
        concept_signals = ["conceito", "define-se", "entende-se por", "consiste em",
                          "é a obrigação", "trata-se de", "pode ser definido"]
        if any(s in text_lower for s in concept_signals):
            return "conceito"
        return "indefinida"

    # Return the position with most signals
    return max(scores, key=scores.get)


def synthesize(blocks: List[DoctrinalBlock], legal_issues: Dict = None) -> Dict:
    """Produce structured doctrinal synthesis from doctrinal blocks.

    This is Stage 2 of the Legal Reasoning Pipeline.
    NO final answer. Only structured doctrinal landscape.

    Args:
        blocks: DoctrinalBlock objects from Doctrine Graph
        legal_issues: Output from Legal Issue Extractor (Stage 1)

    Returns:
        Structured synthesis dict
    """
    if not blocks:
        return {
            "doctrinal_positions": [],
            "convergence_points": [],
            "divergence_points": [],
            "temporal_evolution": [],
            "position_summary": "Nenhuma fonte doutrinária encontrada.",
        }

    # Build positions by author
    positions = []
    for block in blocks:
        # Detect position type for each chunk in the block
        chunk_positions = [detect_doctrinal_position(text) for text in block.chunks]
        # Most common position in the block
        if chunk_positions:
            from collections import Counter
            most_common = Counter(chunk_positions).most_common(1)[0][0]
        else:
            most_common = "indefinida"

        positions.append({
            "author": block.author,
            "work": block.work_title,
            "year": block.year,
            "chapter": block.chapter,
            "position_type": most_common,
            "aggregated_score": block.aggregated_score,
            "chunk_count": len(block.chunks),
            "pages": block.pages,
            "key_excerpts": [c[:200] for c in block.chunks[:3]],
        })

    # Detect convergence (same position type across authors)
    convergence = []
    divergence = []

    authors = list(set(p["author"] for p in positions if p["author"]))
    if len(authors) >= 2:
        # Group positions by type
        by_type = {}
        for pos in positions:
            t = pos["position_type"]
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(pos["author"])

        for pos_type, pos_authors in by_type.items():
            unique_authors = list(set(pos_authors))
            if len(unique_authors) >= 2:
                convergence.append({
                    "type": pos_type,
                    "authors": unique_authors,
                    "note": f"{len(unique_authors)} autores convergem na posição {pos_type}",
                })

        # Detect divergence (different position types for same topic)
        author_positions = {}
        for pos in positions:
            if pos["author"] not in author_positions:
                author_positions[pos["author"]] = set()
            author_positions[pos["author"]].add(pos["position_type"])

        author_list = list(author_positions.keys())
        for i in range(len(author_list)):
            for j in range(i + 1, len(author_list)):
                a, b = author_list[i], author_list[j]
                diff = author_positions[a].symmetric_difference(author_positions[b])
                if diff:
                    divergence.append({
                        "author_a": a,
                        "author_b": b,
                        "positions_a": list(author_positions[a]),
                        "positions_b": list(author_positions[b]),
                        "divergent_types": list(diff),
                    })

    # Temporal evolution
    evolution = []
    years = sorted(set(p["year"] for p in positions if p["year"]))
    if len(years) >= 2 and (years[-1] - years[0]) > 5:
        evolution.append({
            "oldest_year": years[0],
            "newest_year": years[-1],
            "span": years[-1] - years[0],
            "authors_by_year": {
                y: [p["author"] for p in positions if p["year"] == y]
                for y in years
            },
        })

    synthesis = {
        "doctrinal_positions": positions,
        "convergence_points": convergence,
        "divergence_points": divergence,
        "temporal_evolution": evolution,
        "position_summary": _build_summary(positions, convergence, divergence),
    }

    logger.info(
        f"Doctrine Synthesizer: {len(positions)} positions, "
        f"{len(convergence)} convergences, {len(divergence)} divergences"
    )

    return synthesis


def _build_summary(positions, convergence, divergence) -> str:
    """Build human-readable summary for LLM context."""
    parts = []

    if not positions:
        return "Nenhuma posição doutrinária identificada."

    parts.append("SÍNTESE DOUTRINÁRIA (gerada automaticamente):")

    # Authors found
    authors = list(set(p["author"] for p in positions if p["author"]))
    parts.append(f"Autores no contexto: {', '.join(authors) if authors else 'não identificados'}")

    # Position types found
    types = set(p["position_type"] for p in positions)
    type_labels = {
        "majoritaria": "posição majoritária",
        "minoritaria": "posição minoritária",
        "critica": "posição crítica",
        "historica": "perspectiva histórica",
        "conceito": "definição conceitual",
        "indefinida": "posição não classificada",
    }
    type_names = [type_labels.get(t, t) for t in types]
    parts.append(f"Tipos de posição: {', '.join(type_names)}")

    if convergence:
        parts.append(f"Pontos de convergência: {len(convergence)}")
    if divergence:
        parts.append(f"Divergências detectadas: {len(divergence)}")
        for d in divergence:
            parts.append(f"  → {d['author_a']} vs {d['author_b']}")

    return "\n".join(parts)


def build_applicator_context(synthesis: Dict, blocks: List[DoctrinalBlock]) -> str:
    """Build the final context for Stage 3 (Legal Applicator).

    Combines structured synthesis + doctrinal block texts
    into a format optimized for legal opinion generation.
    """
    parts = []

    # Synthesis summary
    parts.append("=" * 60)
    parts.append("CONTEXTO DOUTRINÁRIO ESTRUTURADO")
    parts.append("=" * 60)
    parts.append(synthesis.get("position_summary", ""))

    # Doctrinal blocks organized by author
    parts.append("")
    for block in blocks:
        parts.append(f"\n{'─' * 50}")
        parts.append(block.to_context_string())

    # Divergence notes
    divergences = synthesis.get("divergence_points", [])
    if divergences:
        parts.append(f"\n{'=' * 60}")
        parts.append("⚠ DIVERGÊNCIAS DOUTRINÁRIAS IDENTIFICADAS")
        for d in divergences:
            parts.append(f"  {d['author_a']}: {d['positions_a']}")
            parts.append(f"  {d['author_b']}: {d['positions_b']}")
        parts.append("→ A resposta DEVE apresentar TODAS as posições.")

    return "\n".join(parts)
