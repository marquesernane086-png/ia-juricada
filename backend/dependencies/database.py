"""Database dependency — MongoDB via FastAPI Depends()."""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
import os

_client = None
_db = None


def get_db() -> AsyncIOMotorDatabase:
    """FastAPI dependency for MongoDB database."""
    global _client, _db
    if _db is None:
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "jurista_ai")
        _client = AsyncIOMotorClient(mongo_url)
        _db = _client[db_name]
    return _db


def close_db():
    """Close MongoDB connection."""
    global _client
    if _client:
        _client.close()
