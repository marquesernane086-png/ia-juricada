"""Chat Service - Orchestrates the full RAG pipeline for legal questions.

Pipeline:
  1. Vector Retrieval (vector_service)
  2. Doctrine Comparator (doctrine_comparator)  
  3. Legal Reasoning Agent (reasoning_service)
  4. Citation Guardian (citation_guardian)
  5. Final Response
"""

import time
import logging
from typing import Dict, List, Optional

from services import vector_service, reasoning_service, citation_guardian, doctrine_comparator, legal_issue_extractor
from models.schemas import ChatResponse, SourceReference

logger = logging.getLogger(__name__)


async def process_question(
    question: str,
    session_id: str,
    max_sources: int = 15,
    where_filter: Optional[Dict] = None
) -> ChatResponse:
    """Process a legal question through the full agent pipeline.
    
    Pipeline:
    0. Legal Issue Extractor → decompose question
    1. Vector Retrieval → semantic search with enhanced query
    2. Doctrine Comparator → analyze positions, detect divergence
    3. Legal Reasoning Agent → generate structured response
    4. Citation Guardian → validate all citations
    5. Final Response → deliver to user
    """
    start_time = time.time()
    
    # =========================================================
    # STEP 0: LEGAL ISSUE EXTRACTOR
    # =========================================================
    logger.info(f"[0/5] Legal Issue Extractor: {question[:80]}...")
    legal_issues = legal_issue_extractor.extract_legal_issues(question)
    enhanced_query = legal_issue_extractor.build_enhanced_query(question, legal_issues)
    
    logger.info(
        f"  Area: {legal_issues.get('legal_area')} | "
        f"Instituto: {legal_issues.get('legal_institute')} | "
        f"Keywords: {legal_issues.get('keywords_for_retrieval', [])[:5]}"
    )
    
    # =========================================================
    # STEP 1: VECTOR RETRIEVAL
    # =========================================================
    logger.info(f"[1/5] Vector Retrieval...")
    search_results = vector_service.search(
        query=enhanced_query,
        n_results=max_sources,
        where_filter=where_filter
    )
    
    # Filter low-relevance results
    MIN_RELEVANCE_SCORE = 0.20
    filtered_results = [r for r in search_results if r.get("score", 0) >= MIN_RELEVANCE_SCORE]
    logger.info(f"  Retrieved: {len(search_results)} → Filtered: {len(filtered_results)}")
    
    if not filtered_results:
        processing_time = time.time() - start_time
        return ChatResponse(
            answer=(
                "## RELATÓRIO\n\n"
                "Não foram encontradas fontes doutrinárias indexadas no acervo para responder "
                "a esta questão. Para que o JuristaAI possa fornecer fundamentação doutrinária "
                "adequada, é necessário que livros jurídicos relevantes ao tema sejam indexados "
                "no sistema.\n\n"
                "**Recomendação:** Faça o upload de obras doutrinárias relacionadas ao tema "
                "consultado para habilitar a pesquisa doutrinária."
            ),
            sources=[],
            session_id=session_id,
            question=question,
            processing_time=round(processing_time, 2),
            chunks_retrieved=0
        )
    
    # =========================================================
    # STEP 2: DOCTRINE COMPARATOR
    # =========================================================
    logger.info("[2/5] Doctrine Comparator: analyzing positions...")
    doctrine_analysis = doctrine_comparator.analyze_doctrine(filtered_results)
    doctrine_context = doctrine_comparator.build_doctrine_context(doctrine_analysis)
    
    summary = doctrine_analysis.get("summary", {})
    logger.info(
        f"  Authors: {summary.get('total_authors', 0)}, "
        f"Divergence: {summary.get('has_divergence', False)}, "
        f"Evolution: {summary.get('has_evolution', False)}, "
        f"Minority: {summary.get('has_minority', False)}"
    )
    
    # =========================================================
    # STEP 3: LEGAL REASONING AGENT
    # =========================================================
    logger.info("[3/5] Legal Reasoning Agent: generating response...")
    answer = reasoning_service.generate_response(
        question=question,
        search_results=filtered_results,
        doctrine_context=doctrine_context
    )
    
    # =========================================================
    # STEP 4: CITATION GUARDIAN
    # =========================================================
    logger.info("[4/5] Citation Guardian: validating citations...")
    validated_answer, citation_report = citation_guardian.validate_response(
        response_text=answer,
        sources=filtered_results
    )
    
    logger.info(
        f"  Citations: {citation_report['total_citations']} total, "
        f"{citation_report['valid']} valid, {citation_report['invalid']} flagged"
    )
    
    # =========================================================
    # STEP 5: BUILD FINAL RESPONSE
    # =========================================================
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
    
    logger.info(f"Pipeline complete: {processing_time:.1f}s")
    
    return ChatResponse(
        answer=validated_answer,
        sources=sources,
        session_id=session_id,
        question=question,
        processing_time=round(processing_time, 2),
        chunks_retrieved=len(filtered_results)
    )
