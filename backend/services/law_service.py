"""Law Service — Busca em legislação indexada.

Collection Qdrant dedicada: jurista_leis
Cada artigo = 1 vetor com metadata completa.

ENABLED = False ate ter leis indexadas.
"""

ENABLED = False

import os
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

QDRANT_DIR = None
COLLECTION_NAME = "jurista_leis"
_client = None


def _get_client():
    global _client, QDRANT_DIR
    if _client is not None:
        return _client

    try:
        from qdrant_client import QdrantClient
        from pathlib import Path

        QDRANT_DIR = str(Path(__file__).parent.parent / "data" / "qdrant_data")
        if not os.path.exists(QDRANT_DIR):
            return None

        _client = QdrantClient(path=QDRANT_DIR)

        collections = [c.name for c in _client.get_collections().collections]
        if COLLECTION_NAME not in collections:
            return None

        info = _client.get_collection(COLLECTION_NAME)
        logger.info(f"LawService: {info.points_count} artigos indexados")
        return _client

    except Exception as e:
        logger.warning(f"LawService init failed: {e}")
        return None


def search_articles(query: str, n_results: int = 10, area: Optional[str] = None) -> List[Dict]:
    """Busca artigos de lei por similaridade semantica."""
    if not ENABLED:
        return []

    client = _get_client()
    if not client:
        return []

    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        query_vector = model.encode(query, normalize_embeddings=True).tolist()

        query_filter = None
        if area:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            query_filter = Filter(
                must=[FieldCondition(key="area", match=MatchValue(value=area))]
            )

        results = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=n_results,
            query_filter=query_filter,
        )

        formatted = []
        for point in results:
            p = point.payload or {}
            formatted.append({
                "artigo": p.get("artigo", ""),
                "norma": p.get("norma", ""),
                "numero_norma": p.get("numero_norma", ""),
                "texto": p.get("texto", ""),
                "area": p.get("area", ""),
                "hierarquia": p.get("hierarquia", ""),
                "peso_normativo": p.get("peso_normativo", 2),
                "score": round(point.score, 4),
            })

        return formatted

    except Exception as e:
        logger.error(f"LawService search error: {e}")
        return []


def get_stats() -> Dict:
    client = _get_client()
    if not client:
        return {"total_artigos": 0, "enabled": ENABLED}
    try:
        info = client.get_collection(COLLECTION_NAME)
        return {"total_artigos": info.points_count, "collection": COLLECTION_NAME, "enabled": ENABLED}
    except Exception:
        return {"total_artigos": 0, "enabled": ENABLED}
