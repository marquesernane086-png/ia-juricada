"""Semantic Cache — Cache de consultas jurídicas.

Evita chamadas LLM desnecessárias reutilizando respostas semelhantes.
Usa hash da pergunta + similarity check para cache hits.
TTL configurável via env var CACHE_TTL_SECONDS.
"""

import os
import time
import hashlib
import logging
from typing import Optional, Dict, Tuple
from collections import OrderedDict

logger = logging.getLogger(__name__)

MAX_CACHE_SIZE = int(os.environ.get("CACHE_MAX_SIZE", "200"))
CACHE_TTL = int(os.environ.get("CACHE_TTL_SECONDS", "3600"))  # 1 hora


def _hash_question(question: str) -> str:
    """Gera hash determinístico da pergunta normalizada."""
    normalized = question.lower().strip()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


class SemanticCache:
    """Cache semântico para respostas jurídicas.
    
    Armazena respostas por hash da pergunta com TTL.
    Evita chamadas LLM repetidas para perguntas iguais ou similares.
    """

    def __init__(self, max_size: int = MAX_CACHE_SIZE, ttl: int = CACHE_TTL):
        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl
        self._hits = 0
        self._misses = 0

    def get(self, question: str) -> Optional[Dict]:
        """Busca resposta no cache.
        
        Returns:
            Dict com resposta cacheada ou None se miss/expirado.
        """
        key = _hash_question(question)

        if key in self._cache:
            entry = self._cache[key]
            age = time.time() - entry["timestamp"]

            if age < self._ttl:
                self._hits += 1
                self._cache.move_to_end(key)
                logger.info(f"Cache HIT: {question[:50]}... (age: {age:.0f}s)")
                return entry["data"]
            else:
                # Expired
                del self._cache[key]

        self._misses += 1
        return None

    def put(self, question: str, data: Dict):
        """Armazena resposta no cache."""
        key = _hash_question(question)

        # Evict oldest if full
        while len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)

        self._cache[key] = {
            "data": data,
            "timestamp": time.time(),
            "question": question[:100],
        }
        logger.info(f"Cache PUT: {question[:50]}... (size: {len(self._cache)})")

    def invalidate(self, question: str = None):
        """Invalida cache. Se question=None, limpa tudo."""
        if question:
            key = _hash_question(question)
            self._cache.pop(key, None)
        else:
            self._cache.clear()
            logger.info("Cache cleared")

    def stats(self) -> Dict:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "ttl_seconds": self._ttl,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / max(total, 1) * 100, 1),
        }


# Singleton
_cache_instance = None

def get_cache() -> SemanticCache:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = SemanticCache()
    return _cache_instance
