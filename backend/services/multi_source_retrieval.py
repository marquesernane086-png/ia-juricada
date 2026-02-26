"""Multi-Source Retrieval — Busca paralela em doutrina, legislação, jurisprudência.

NÃO substitui search() atual. Função adicional.
Ativar via MULTI_SOURCE_ENABLED=true
"""

import os
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

ENABLED = os.environ.get("MULTI_SOURCE_ENABLED", "false").lower() == "true"


def search_multi_source(
    query: str,
    n_doctrine: int = 12,
    n_legislation: int = 8,
    n_jurisprudence: int = 8,
    filters: Optional[Dict] = None,
) -> Dict[str, List[Dict]]:
    """Busca paralela em múltiplas fontes jurídicas.

    Returns:
        {
            "doctrine": [...],
            "legislation": [...],
            "jurisprudence": [...]
        }
    """
    results = {
        "doctrine": [],
        "legislation": [],
        "jurisprudence": [],
    }

    # Doctrine (existing vector_service)
    try:
        from services import vector_service
        all_results = vector_service.search(query, n_results=n_doctrine + n_legislation)

        for r in all_results:
            meta = r.get("metadata", {})
            tipo = meta.get("tipo_documento", meta.get("fonte_normativa", "doutrina"))

            if tipo in ("lei", "legislacao", "legislation"):
                if len(results["legislation"]) < n_legislation:
                    r["_source_type"] = "legislation"
                    results["legislation"].append(r)
            elif tipo in ("jurisprudencia", "jurisprudence"):
                if len(results["jurisprudence"]) < n_jurisprudence:
                    r["_source_type"] = "jurisprudence"
                    results["jurisprudence"].append(r)
            else:
                if len(results["doctrine"]) < n_doctrine:
                    r["_source_type"] = "doctrine"
                    results["doctrine"].append(r)
    except Exception as e:
        logger.error(f"Multi-source search error: {e}")

    # Legislation service (if enabled)
    try:
        from services.law_service import ENABLED as LAW_ENABLED, search_articles
        if LAW_ENABLED:
            law_results = search_articles(query, n_results=n_legislation)
            for r in law_results:
                r["_source_type"] = "legislation"
            results["legislation"].extend(law_results)
    except Exception:
        pass

    # Jurisprudence service (if enabled)
    try:
        from services.jurisprudence_service import ENABLED as JURIS_ENABLED, search
        if JURIS_ENABLED:
            juris_results = search(query, n_results=n_jurisprudence)
            for r in juris_results:
                r["_source_type"] = "jurisprudence"
            results["jurisprudence"].extend(juris_results)
    except Exception:
        pass

    logger.info(
        f"[MultiSource] doctrine={len(results['doctrine'])}, "
        f"legislation={len(results['legislation'])}, "
        f"jurisprudence={len(results['jurisprudence'])}"
    )

    return results
