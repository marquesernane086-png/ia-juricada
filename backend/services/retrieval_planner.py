"""Advanced Legal Retrieval Planner — Multi-source legal search orchestrator.

Decides WHICH legal sources to query, in WHICH order, based on question intent.
Respects Brazilian legal hierarchy: Lei > Jurisprudência > Doutrina.

Pipeline position: BEFORE vector retrieval. Replaces single-source search.

Collections:
  jurista_leis            → statutes, codes, articles
  jurista_jurisprudencia  → court decisions  
  jurista_legal_docs      → doctrine books
"""

import os
import re
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# ============================================================
# COLLECTION MAPPING
# ============================================================

COLLECTIONS = {
    "leis": "jurista_leis",
    "jurisprudencia": "jurista_jurisprudencia",
    "doutrina": "jurista_legal_docs",
}

# ============================================================
# INTENT CLASSIFICATION
# ============================================================

INTENT_KEYWORDS = {
    "consulta_legal": [
        "qual o artigo", "qual artigo", "o que diz a lei", "previsto em lei",
        "dispositivo legal", "base legal", "fundamento legal", "previsão legal",
        "código civil", "código penal", "constituição", "cpc", "cdc", "clt",
        "lei nº", "decreto", "art.", "artigo",
    ],
    "caso_pratico": [
        "caso", "situação", "hipótese", "imagine", "suponha", "exemplo",
        "joão", "maria", "empresa", "contrato", "comprou", "vendeu",
        "acidente", "bateu", "danificou", "rescisão", "demitido",
    ],
    "jurisprudencia": [
        "jurisprudência", "entendimento do stj", "entendimento do stf",
        "decisão", "precedente", "súmula", "tribunal", "julgado",
        "posição do tribunal", "leading case",
    ],
    "interpretacao_doutrinaria": [
        "segundo a doutrina", "doutrinadores", "autores", "interpretação",
        "corrente", "posição doutrinária", "entendimento doutrinário",
        "majoritária", "minoritária",
    ],
    "conceito_juridico": [
        "o que é", "conceito de", "defina", "explique", "significa",
        "natureza jurídica", "classificação", "elementos", "pressupostos",
        "requisitos", "características",
    ],
}

# Retrieval order per intent
RETRIEVAL_PLANS = {
    "consulta_legal": [
        {"source": "leis", "top_k": 10},
        {"source": "jurisprudencia", "top_k": 8},
    ],
    "caso_pratico": [
        {"source": "leis", "top_k": 8},
        {"source": "jurisprudencia", "top_k": 8},
        {"source": "doutrina", "top_k": 6},
    ],
    "jurisprudencia": [
        {"source": "jurisprudencia", "top_k": 12},
        {"source": "leis", "top_k": 5},
        {"source": "doutrina", "top_k": 5},
    ],
    "interpretacao_doutrinaria": [
        {"source": "leis", "top_k": 5},
        {"source": "doutrina", "top_k": 12},
        {"source": "jurisprudencia", "top_k": 5},
    ],
    "conceito_juridico": [
        {"source": "doutrina", "top_k": 12},
        {"source": "leis", "top_k": 6},
    ],
}

# ============================================================
# AUTHORITY WEIGHTS (court hierarchy)
# ============================================================

COURT_AUTHORITY = {
    "STF": 40,
    "STJ": 30,
    "TST": 25,
    "TSE": 25,
    "TRF": 15, "TRF1": 15, "TRF2": 15, "TRF3": 15, "TRF4": 15, "TRF5": 15,
    "TJ": 15, "TJSP": 15, "TJRJ": 15, "TJMG": 15, "TJRS": 15,
    "TRT": 10,
}

LAW_BOOST = 30  # Laws always boosted in final ranking


# ============================================================
# INTENT CLASSIFIER
# ============================================================

def classify_intent(question: str) -> str:
    """Classify question intent for retrieval planning."""
    q_lower = question.lower()

    scores = {}
    for intent, keywords in INTENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in q_lower)
        if score > 0:
            scores[intent] = score

    if not scores:
        return "conceito_juridico"  # default: doctrinal lookup

    return max(scores, key=scores.get)


# ============================================================
# PLAN RETRIEVAL
# ============================================================

def plan_retrieval(question: str) -> Dict:
    """Create retrieval plan based on question intent.

    Returns:
        {
            "intent": "caso_pratico",
            "sources": [
                {"collection": "jurista_leis", "top_k": 8, "source": "leis"},
                {"collection": "jurista_jurisprudencia", "top_k": 8, "source": "jurisprudencia"},
                {"collection": "jurista_legal_docs", "top_k": 6, "source": "doutrina"}
            ]
        }
    """
    intent = classify_intent(question)
    plan_template = RETRIEVAL_PLANS.get(intent, RETRIEVAL_PLANS["conceito_juridico"])

    sources = []
    for step in plan_template:
        source_name = step["source"]
        collection = COLLECTIONS.get(source_name, "")
        if collection:
            sources.append({
                "collection": collection,
                "top_k": step["top_k"],
                "source": source_name,
            })

    plan = {
        "intent": intent,
        "sources": sources,
    }

    logger.info(
        f"[Planner] Intent: {intent} | "
        f"Order: {' → '.join(s['source'].upper() for s in sources)}"
    )

    return plan


# ============================================================
# EXECUTE PLAN
# ============================================================

def execute_plan(plan: Dict, question: str, available_services: Dict = None) -> List[Dict]:
    """Execute retrieval plan across multiple vector databases.

    Args:
        plan: Output from plan_retrieval()
        question: Original question
        available_services: Dict mapping source names to search functions
            e.g. {"doutrina": vector_service.search, "leis": law_service.search_articles}

    Returns:
        Unified, deduplicated, re-ranked list of results
    """
    available_services = available_services or {}
    all_results = []
    stats = {}

    for step in plan.get("sources", []):
        source = step["source"]
        top_k = step["top_k"]
        collection = step["collection"]

        search_fn = available_services.get(source)
        if not search_fn:
            logger.info(f"[Planner] {source.upper()}: not available (skipped)")
            stats[source] = 0
            continue

        try:
            results = search_fn(question, n_results=top_k)
            # Tag each result with source type
            for r in results:
                r["_source_type"] = source
                r["_collection"] = collection
            all_results.extend(results)
            stats[source] = len(results)
            logger.info(f"[Planner] {source.upper()}: {len(results)} results")
        except Exception as e:
            logger.error(f"[Planner] {source.upper()} error: {e}")
            stats[source] = 0

    # Deduplicate
    deduped = _deduplicate(all_results)

    # Re-rank with legal hierarchy
    ranked = _rerank(deduped)

    logger.info(
        f"[Planner] Retrieved: {' | '.join(f'{k}={v}' for k, v in stats.items())} "
        f"| After dedup: {len(deduped)} | Final: {len(ranked)}"
    )

    return ranked


# ============================================================
# DEDUPLICATION
# ============================================================

def _deduplicate(results: List[Dict]) -> List[Dict]:
    """Remove duplicate results across collections."""
    seen = set()
    deduped = []

    for r in results:
        meta = r.get("metadata", r.get("payload", {}))
        source = r.get("_source_type", "")

        # Generate dedup key based on source type
        if source == "leis":
            key = f"lei_{meta.get('numero_norma', '')}_{meta.get('artigo', '')}"
        elif source == "jurisprudencia":
            key = f"juris_{meta.get('processo', '')}_{meta.get('tribunal', '')}"
        else:
            key = f"doc_{meta.get('doctrine_id', meta.get('hash', ''))}"

        # Fallback to text hash
        if not key or key in ("lei__", "juris__", "doc_"):
            text = r.get("text", "")[:200]
            key = f"text_{hash(text)}"

        if key not in seen:
            seen.add(key)
            deduped.append(r)

    return deduped


# ============================================================
# RE-RANKING WITH LEGAL HIERARCHY
# ============================================================

def _rerank(results: List[Dict]) -> List[Dict]:
    """Re-rank results respecting legal hierarchy."""
    for r in results:
        base_score = r.get("score", 0.0)
        source = r.get("_source_type", "")
        meta = r.get("metadata", r.get("payload", {}))
        boost = 0.0

        # LAW DOMINANCE: laws always appear first
        if source == "leis":
            boost += LAW_BOOST
            # Extra boost for constitutional articles
            hierarquia = meta.get("hierarquia", "")
            if hierarquia == "constituicao":
                boost += 20

        # COURT AUTHORITY: higher courts get more weight
        elif source == "jurisprudencia":
            tribunal = meta.get("tribunal", "")
            boost += COURT_AUTHORITY.get(tribunal, 5)
            # Ementa gets extra boost
            if meta.get("is_ementa"):
                boost += 10

        # DOCTRINE: base boost by normative weight
        elif source == "doutrina":
            peso = meta.get("peso_normativo", 1)
            try:
                boost += int(peso) * 2
            except (ValueError, TypeError):
                pass

        r["_final_score"] = round(base_score * 100 + boost, 2)

    # Sort: highest final score first
    results.sort(key=lambda x: x.get("_final_score", 0), reverse=True)

    return results
