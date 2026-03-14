"""Chat routes - Legal question answering API."""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from models.schemas import ChatRequest, ChatResponse, SystemStats
from services import chat_service, vector_service
from dependencies.auth import require_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

db: Optional[AsyncIOMotorDatabase] = None

CHAT_TIMEOUT = 60  # seconds


def set_db(database: AsyncIOMotorDatabase):
    global db
    db = database


@router.post("", response_model=ChatResponse, dependencies=[Depends(require_api_key)])
async def ask_question(request: ChatRequest):
    """Ask a legal question and receive a doctrinal response."""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    try:
        response = await asyncio.wait_for(
            chat_service.process_question(
                question=request.question,
                session_id=request.session_id,
                max_sources=request.max_sources
            ),
            timeout=CHAT_TIMEOUT
        )
        return response
    except asyncio.TimeoutError:
        logger.error(f"Chat timeout ({CHAT_TIMEOUT}s): {request.question[:80]}")
        raise HTTPException(status_code=504, detail=f"Tempo limite de {CHAT_TIMEOUT}s excedido.")
    except Exception as e:
        logger.error(f"Error processing question: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/stats", response_model=SystemStats)
async def get_stats():
    """Get system statistics."""
    import os

    vector_stats = vector_service.get_stats()

    total_docs = await db.documents.count_documents({})
    indexed_docs = await db.documents.count_documents({"status": "indexed"})

    return SystemStats(
        total_documents=total_docs,
        indexed_documents=indexed_docs,
        total_chunks=vector_stats.get("total_chunks", 0),
        vector_store_size=vector_stats.get("total_chunks", 0),
        embedding_model=os.environ.get('EMBEDDING_MODEL', 'unknown'),
        llm_model=os.environ.get('LLM_MODEL', 'unknown')
    )
