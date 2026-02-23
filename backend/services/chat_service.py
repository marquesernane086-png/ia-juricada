"""Chat Service - Orchestrates the full RAG pipeline for legal questions."""

import time
import logging
from typing import Dict, List, Optional

from services import vector_service, reasoning_service
from models.schemas import ChatResponse, SourceReference

logger = logging.getLogger(__name__)


async def process_question(
    question: str,
    session_id: str,
    max_sources: int = 10,
    where_filter: Optional[Dict] = None
) -> ChatResponse:
    """Process a legal question through the full RAG pipeline.
    
    Pipeline:
    1. Semantic search in vector store
    2. Apply temporal weighting
    3. Group by author
    4. Generate doctrinal reasoning response
    
    Args:
        question: User's legal question
        session_id: Session identifier
        max_sources: Maximum number of source chunks to retrieve
        where_filter: Optional metadata filter
    
    Returns:
        ChatResponse with answer and sources
    """
    start_time = time.time()
    
    # Step 1: Semantic search
    logger.info(f"Processing question: {question[:100]}...")
    search_results = vector_service.search(
        query=question,
        n_results=max_sources,
        where_filter=where_filter
    )
    
    # Step 1.5: Filter out low-relevance results (score threshold)
    # LlamaIndex scores are typically lower than cosine similarity
    # Use a low threshold to not miss relevant content
    MIN_RELEVANCE_SCORE = 0.20
    filtered_results = [r for r in search_results if r.get("score", 0) >= MIN_RELEVANCE_SCORE]
    logger.info(f"Results: {len(search_results)} total, {len(filtered_results)} above threshold ({MIN_RELEVANCE_SCORE})")
    
    # Step 2: Generate doctrinal response
    if filtered_results:
        answer = reasoning_service.generate_response(question, filtered_results)
    else:
        answer = (
            "## RELATÓRIO\n\n"
            "Não foram encontradas fontes doutrinárias indexadas no acervo para responder "
            "a esta questão. Para que o JuristaAI possa fornecer fundamentação doutrinária "
            "adequada, é necessário que livros jurídicos relevantes ao tema sejam indexados "
            "no sistema.\n\n"
            "**Recomendação:** Faça o upload de obras doutrinárias relacionadas ao tema "
            "consultado para habilitar a pesquisa doutrinária."
        )
    
    # Step 3: Build source references
    sources = []
    for result in filtered_results:
        meta = result.get("metadata", {})
        year = meta.get("year")
        if isinstance(year, str):
            try:
                year = int(year) if year else None
            except ValueError:
                year = None
        
        page = meta.get("page")
        if isinstance(page, str):
            try:
                page = int(page) if page else None
            except ValueError:
                page = None
        
        sources.append(SourceReference(
            author=meta.get("author", "Desconhecido"),
            title=meta.get("title", "Obra não identificada"),
            year=year,
            chunk_text=result["text"][:300] + "..." if len(result["text"]) > 300 else result["text"],
            relevance_score=result.get("score", 0),
            page=page
        ))
    
    processing_time = time.time() - start_time
    
    return ChatResponse(
        answer=answer,
        sources=sources,
        session_id=session_id,
        question=question,
        processing_time=round(processing_time, 2),
        chunks_retrieved=len(filtered_results)
    )
