"""VectorStoreService — Abstraction layer for vector database operations.

Provides unified interface for search/insert/delete/health.
Allows future migration to AWS/Cloud without changing business logic.

Backends supported: Qdrant (remote/local), LlamaIndex fallback.
"""

import os
import time
import logging
from typing import List, Dict, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class VectorStoreBackend(ABC):
    """Abstract interface for vector store backends."""

    @abstractmethod
    def search(self, query: str, n_results: int = 10, filters: Optional[Dict] = None) -> List[Dict]:
        pass

    @abstractmethod
    def insert(self, text: str, metadata: Dict) -> int:
        pass

    @abstractmethod
    def delete(self, doc_id: str) -> int:
        pass

    @abstractmethod
    def health_check(self) -> Dict:
        pass

    @abstractmethod
    def get_stats(self) -> Dict:
        pass


class VectorStoreService:
    """Unified vector store service with retry, logging, and metrics.
    
    Wraps the existing vector_service module with production-grade features.
    """

    def __init__(self):
        self._backend = None
        self._search_count = 0
        self._error_count = 0
        self._total_search_time = 0.0
        self._max_retries = int(os.environ.get("VECTOR_MAX_RETRIES", "2"))
        self._timeout = int(os.environ.get("VECTOR_TIMEOUT", "30"))

    def _get_backend(self):
        """Lazy-load the actual vector service."""
        if self._backend is None:
            from services import vector_service
            self._backend = vector_service
        return self._backend

    def search(self, query: str, n_results: int = 10, filters: Optional[Dict] = None) -> List[Dict]:
        """Search with retry and metrics."""
        start = time.time()
        last_error = None

        for attempt in range(self._max_retries + 1):
            try:
                backend = self._get_backend()
                results = backend.search(query, n_results=n_results, where_filter=filters)
                elapsed = time.time() - start
                self._search_count += 1
                self._total_search_time += elapsed

                if elapsed > 5.0:
                    logger.warning(f"Slow search: {elapsed:.1f}s for: {query[:60]}")

                return results

            except Exception as e:
                last_error = e
                self._error_count += 1
                if attempt < self._max_retries:
                    logger.warning(f"Search retry {attempt+1}/{self._max_retries}: {e}")
                    time.sleep(0.5 * (attempt + 1))

        logger.error(f"Search failed after {self._max_retries+1} attempts: {last_error}")
        return []

    def insert(self, text: str, metadata: Dict) -> int:
        """Insert document with error handling."""
        try:
            return self._get_backend().add_document(text, metadata)
        except Exception as e:
            logger.error(f"Insert failed: {e}")
            return 0

    def delete(self, doc_id: str) -> int:
        """Delete document chunks."""
        try:
            return self._get_backend().delete_document_chunks(doc_id)
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return 0

    def health_check(self) -> Dict:
        """Check vector store health."""
        try:
            stats = self._get_backend().get_stats()
            return {
                "status": "healthy" if stats.get("total_chunks", 0) >= 0 else "empty",
                "backend": stats.get("backend", "unknown"),
                "chunks": stats.get("total_chunks", 0),
                "search_count": self._search_count,
                "error_count": self._error_count,
                "avg_search_ms": round(self._total_search_time / max(self._search_count, 1) * 1000, 1),
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def get_stats(self) -> Dict:
        return self._get_backend().get_stats()

    def reset(self):
        self._get_backend().reset_index()
        self._backend = None


# Singleton
_instance = None

def get_vector_store() -> VectorStoreService:
    global _instance
    if _instance is None:
        _instance = VectorStoreService()
    return _instance
