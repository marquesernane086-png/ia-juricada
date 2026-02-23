"""Ingestion Service - Reads PDF and EPUB files, extracts text and metadata."""

import fitz  # PyMuPDF
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import hashlib
import os
import re
import logging
from typing import Dict, Optional, Tuple, List
from pathlib import Path

logger = logging.getLogger(__name__)


def compute_file_hash(file_path: str) -> str:
    """Compute SHA256 hash of a file for deduplication."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def extract_pdf_text(file_path: str) -> Tuple[str, Dict]:
    """Extract text and metadata from a PDF file.
    
    Returns:
        Tuple of (full_text, metadata_dict)
    """
    try:
        doc = fitz.open(file_path)
        metadata = doc.metadata or {}
        
        full_text = ""
        page_texts = []
        
        total_pages = len(doc)
        
        for page_num in range(total_pages):
            page = doc[page_num]
            text = page.get_text("text")
            if text.strip():
                page_texts.append({
                    "page": page_num + 1,
                    "text": text.strip()
                })
                full_text += text + "\n\n"
        
        doc.close()
        
        extracted_meta = {
            "title": metadata.get("title", "") or "",
            "author": metadata.get("author", "") or "",
            "total_pages": total_pages,
            "subject": metadata.get("subject", "") or "",
            "creator": metadata.get("creator", "") or "",
            "producer": metadata.get("producer", "") or "",
            "page_texts": page_texts
        }
        
        # Try to extract year from metadata or text
        year = _extract_year(metadata, full_text[:5000])
        if year:
            extracted_meta["year"] = year
        
        logger.info(f"PDF extracted: {len(page_texts)} pages, {len(full_text)} chars")
        return full_text, extracted_meta
        
    except Exception as e:
        logger.error(f"Error extracting PDF: {e}")
        raise


def extract_epub_text(file_path: str) -> Tuple[str, Dict]:
    """Extract text and metadata from an EPUB file.
    
    Returns:
        Tuple of (full_text, metadata_dict)
    """
    try:
        book = epub.read_epub(file_path, options={'ignore_ncx': True})
        
        # Extract metadata
        title = ""
        author = ""
        year = None
        
        title_meta = book.get_metadata('DC', 'title')
        if title_meta:
            title = title_meta[0][0] if title_meta[0] else ""
        
        author_meta = book.get_metadata('DC', 'creator')
        if author_meta:
            author = author_meta[0][0] if author_meta[0] else ""
        
        date_meta = book.get_metadata('DC', 'date')
        if date_meta:
            date_str = date_meta[0][0] if date_meta[0] else ""
            year_match = re.search(r'(\d{4})', date_str)
            if year_match:
                year = int(year_match.group(1))
        
        # Extract text from HTML items
        full_text = ""
        chapter_texts = []
        chapter_num = 0
        
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            content = item.get_content()
            soup = BeautifulSoup(content, 'lxml')
            text = soup.get_text(separator='\n', strip=True)
            
            if text.strip() and len(text.strip()) > 50:
                chapter_num += 1
                chapter_texts.append({
                    "chapter": chapter_num,
                    "text": text.strip()
                })
                full_text += text + "\n\n"
        
        extracted_meta = {
            "title": title,
            "author": author,
            "year": year,
            "total_pages": chapter_num,
            "chapter_texts": chapter_texts
        }
        
        # Try to extract year from text if not in metadata
        if not year:
            year = _extract_year({}, full_text[:5000])
            if year:
                extracted_meta["year"] = year
        
        logger.info(f"EPUB extracted: {chapter_num} chapters, {len(full_text)} chars")
        return full_text, extracted_meta
        
    except Exception as e:
        logger.error(f"Error extracting EPUB: {e}")
        raise


def extract_text(file_path: str) -> Tuple[str, Dict]:
    """Extract text from a file based on its extension."""
    ext = Path(file_path).suffix.lower()
    
    if ext == '.pdf':
        return extract_pdf_text(file_path)
    elif ext == '.epub':
        return extract_epub_text(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def _extract_year(metadata: Dict, text_sample: str) -> Optional[int]:
    """Try to extract publication year from metadata or text."""
    # Try from metadata date fields
    for key in ['creationDate', 'modDate', 'date']:
        if key in metadata and metadata[key]:
            match = re.search(r'(19[5-9]\d|20[0-2]\d)', str(metadata[key]))
            if match:
                return int(match.group(1))
    
    # Try from text - look for common patterns in Brazilian legal books
    patterns = [
        r'(?:edição|edicao|ed\.)\s*(?:de\s+)?(19[5-9]\d|20[0-2]\d)',
        r'(?:copyright|©)\s*(19[5-9]\d|20[0-2]\d)',
        r'(?:publicado|publicação)\s*(?:em\s+)?(19[5-9]\d|20[0-2]\d)',
        r'(19[5-9]\d|20[0-2]\d)\s*(?:by|por)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text_sample, re.IGNORECASE)
        if match:
            return int(match.group(1))
    
    return None


def _extract_edition(text_sample: str) -> Optional[str]:
    """Try to extract edition information from text."""
    patterns = [
        r'(\d+)[ªaº]?\s*(?:edição|edicao|ed\.)',
        r'(?:edição|edicao|ed\.)\s*(\d+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text_sample, re.IGNORECASE)
        if match:
            return f"{match.group(1)}ª edição"
    
    return None


def guess_metadata_from_filename(filename: str) -> Dict:
    """Try to extract metadata from filename patterns.
    
    Common patterns:
    - Author - Title (Year).pdf
    - Title - Author.pdf
    """
    name = Path(filename).stem
    result = {}
    
    # Try to find year in filename
    year_match = re.search(r'[\(\[](\d{4})[\)\]]', name)
    if year_match:
        result['year'] = int(year_match.group(1))
        name = name[:year_match.start()] + name[year_match.end():]
    
    # Try to split by common separators
    parts = re.split(r'\s*[-–—]\s*', name.strip(), maxsplit=1)
    if len(parts) == 2:
        result['author'] = parts[0].strip()
        result['title'] = parts[1].strip()
    else:
        result['title'] = name.strip()
    
    return result
