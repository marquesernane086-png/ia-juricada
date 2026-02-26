"""Config — Separação DEV/PROD com variáveis de ambiente.

Toda configuração centralizada aqui.
Nenhuma URL fixa no código.
"""

import os


class Config:
    """Configuração centralizada do JuristaAI."""

    # Environment
    ENV = os.environ.get("JURISTA_ENV", "development")  # development, production

    # MongoDB
    MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    DB_NAME = os.environ.get("DB_NAME", "jurista_ai")

    # LLM
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.3"))
    LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "4000"))
    INTEGRATION_PROXY_URL = os.environ.get("INTEGRATION_PROXY_URL", "https://integrations.emergentagent.com")

    # Embeddings
    EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

    # Qdrant
    QDRANT_URL = os.environ.get("QDRANT_URL", "")  # Remote Qdrant
    QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")  # For Qdrant Cloud
    QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "jurista_legal_docs")

    # Vector search
    VECTOR_MAX_RETRIES = int(os.environ.get("VECTOR_MAX_RETRIES", "2"))
    VECTOR_TIMEOUT = int(os.environ.get("VECTOR_TIMEOUT", "30"))
    BROAD_RECALL_TOP_K = int(os.environ.get("BROAD_RECALL_TOP_K", "40"))
    FINAL_CHUNKS = int(os.environ.get("FINAL_CHUNKS", "12"))

    # Cache
    CACHE_MAX_SIZE = int(os.environ.get("CACHE_MAX_SIZE", "200"))
    CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "3600"))

    # Chunking
    CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "1000"))
    CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "200"))

    # CORS
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")

    @classmethod
    def is_production(cls) -> bool:
        return cls.ENV == "production"

    @classmethod
    def summary(cls) -> dict:
        return {
            "env": cls.ENV,
            "db": cls.DB_NAME,
            "llm": cls.LLM_MODEL,
            "embedding": cls.EMBEDDING_MODEL,
            "qdrant_remote": bool(cls.QDRANT_URL),
            "qdrant_collection": cls.QDRANT_COLLECTION,
            "cache_ttl": cls.CACHE_TTL_SECONDS,
            "vector_retries": cls.VECTOR_MAX_RETRIES,
        }
