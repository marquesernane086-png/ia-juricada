"""JurisprudenceAI Service — Busca em jurisprudência indexada.

Subsistema independente do DoctrineAI.
Usa collection Qdrant separada: jurista_jurisprudencia

NAO ativado no pipeline principal ainda.
Preparado para futuro Jurisprudence Agent.
"""

ENABLED = False  # Ativar quando houver jurisprudência indexada

import os
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

QDRANT_DIR = None
COLLECTION_NAME = "jurista_jurisprudencia"
_client = None


def _get_client():
    """Inicializa Qdrant client para jurisprudência."""
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

        # Verificar se collection existe
        collections = [c.name for c in _client.get_collections().collections]
        if COLLECTION_NAME not in collections:
            logger.info(f"Collection '{COLLECTION_NAME}' nao existe ainda")
            return None

        info = _client.get_collection(COLLECTION_NAME)
        logger.info(f"JurisprudenceAI: {info.points_count} decisoes indexadas")
        return _client

    except Exception as e:
        logger.warning(f"JurisprudenceAI init failed: {e}")
        return None


def search(query: str, n_results: int = 10, tribunal: Optional[str] = None) -> List[Dict]:
    """Busca jurisprudência por similaridade semântica.

    Args:
        query: Texto da busca
        n_results: Número de resultados
        tribunal: Filtrar por tribunal (STJ, STF, etc.)

    Returns:
        Lista de decisões com texto + metadados + score
    """
    if not ENABLED:
        return []

    client = _get_client()
    if not client:
        return []

    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        query_vector = model.encode(query, normalize_embeddings=True).tolist()

        # Filtro por tribunal se especificado
        query_filter = None
        if tribunal:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            query_filter = Filter(
                must=[FieldCondition(key="tribunal", match=MatchValue(value=tribunal))]
            )

        results = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=n_results,
            query_filter=query_filter,
        )

        formatted = []
        for point in results:
            payload = point.payload or {}
            formatted.append({
                "text": payload.get("text", ""),
                "score": round(point.score, 4),
                "metadata": {
                    "source_type": "jurisprudencia",
                    "tribunal": payload.get("tribunal", ""),
                    "processo": payload.get("processo", ""),
                    "relator": payload.get("relator", ""),
                    "classe": payload.get("classe", ""),
                    "data_julgamento": payload.get("data_julgamento", ""),
                    "tipo_decisao": payload.get("tipo_decisao", ""),
                    "is_ementa": payload.get("is_ementa", False),
                    "peso_normativo": payload.get("peso_normativo", 3),
                },
            })

        logger.info(f"JurisprudenceAI: {len(formatted)} resultados para: {query[:60]}...")
        return formatted

    except Exception as e:
        logger.error(f"JurisprudenceAI search error: {e}")
        return []


def get_stats() -> Dict:
    """Estatísticas da jurisprudência indexada."""
    client = _get_client()
    if not client:
        return {"total_decisoes": 0, "enabled": ENABLED}

    try:
        info = client.get_collection(COLLECTION_NAME)
        return {
            "total_decisoes": info.points_count,
            "collection": COLLECTION_NAME,
            "enabled": ENABLED,
        }
    except Exception:
        return {"total_decisoes": 0, "enabled": ENABLED}
