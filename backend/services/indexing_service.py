"""Indexing Service - Chunks documents and attaches metadata."""

import os
import re
import logging
from typing import List, Dict, Optional
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

# Legal-aware separators for Brazilian legal texts
LEGAL_SEPARATORS = [
    "\n\nCAPÍTULO",
    "\n\nSEÇÃO",
    "\n\nArt.",
    "\n\nArtigo",
    "\n\n§",
    "\n\n",
    "\n",
    ". ",
    " ",
]


def create_chunks(
    text: str,
    metadata: Dict,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    page_texts: Optional[List[Dict]] = None
) -> List[Dict]:
    """Split text into chunks with metadata.
    
    Args:
        text: Full document text
        metadata: Document metadata (author, title, year, etc.)
        chunk_size: Target chunk size in characters
        chunk_overlap: Overlap between chunks
        page_texts: Optional list of per-page texts for page tracking
    
    Returns:
        List of chunk dicts with text and metadata
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=LEGAL_SEPARATORS,
        length_function=len,
        is_separator_regex=False,
    )
    
    chunks = []
    
    if page_texts:
        # Process page by page for better page tracking
        chunks = _chunk_with_pages(splitter, page_texts, metadata)
    else:
        # Process as a whole
        text_chunks = splitter.split_text(text)
        for i, chunk_text in enumerate(text_chunks):
            if not chunk_text.strip():
                continue
            chunk = _build_chunk(chunk_text, metadata, i)
            chunks.append(chunk)
    
    logger.info(f"Created {len(chunks)} chunks from document '{metadata.get('title', 'unknown')}'")
    return chunks


def _chunk_with_pages(
    splitter: RecursiveCharacterTextSplitter,
    page_texts: List[Dict],
    metadata: Dict
) -> List[Dict]:
    """Chunk text while preserving page numbers."""
    chunks = []
    chunk_index = 0
    
    for page_info in page_texts:
        page_num = page_info.get("page") or page_info.get("chapter", 0)
        text = page_info["text"]
        
        if not text.strip():
            continue
        
        page_chunks = splitter.split_text(text)
        
        for chunk_text in page_chunks:
            if not chunk_text.strip():
                continue
            chunk = _build_chunk(chunk_text, metadata, chunk_index, page_num)
            chunks.append(chunk)
            chunk_index += 1
    
    return chunks


def _build_chunk(text: str, metadata: Dict, index: int, page: Optional[int] = None) -> Dict:
    """Build a chunk dictionary with text and metadata."""
    chunk = {
        "text": text.strip(),
        "metadata": {
            "doc_id": metadata.get("doc_id", ""),
            "author": metadata.get("author", ""),
            "title": metadata.get("title", ""),
            "year": metadata.get("year"),
            "edition": metadata.get("edition", ""),
            "legal_subject": metadata.get("legal_subject", ""),
            "legal_institute": metadata.get("legal_institute", ""),
            "chunk_index": index,
        }
    }
    
    if page is not None:
        chunk["metadata"]["page"] = page
    
    return chunk


def compute_temporal_weight(year: Optional[int]) -> float:
    """Compute temporal weight for doctrinal relevance.
    
    Formula: peso = 1 + ((ano - 1950) / 100)
    
    More recent works get higher weight, but classical works
    are still preserved (never below 1.0).
    """
    if not year:
        return 1.0
    
    weight = 1.0 + ((year - 1950) / 100.0)
    return max(1.0, round(weight, 3))


def clean_text(text: str) -> str:
    """Clean extracted text for better indexing."""
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove page numbers / headers that repeat
    text = re.sub(r'\n\d+\n', '\n', text)
    # Remove common PDF artifacts
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    return text.strip()
