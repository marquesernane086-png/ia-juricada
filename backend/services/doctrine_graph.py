"""Doctrine Graph Layer — Hierarchical doctrinal identity system.

Transforms flat chunk retrieval into doctrine-aware retrieval.
Adds hierarchical identifiers: author_id → work_id → chapter_id → doctrine_id.

This layer operates BETWEEN vector retrieval and reasoning.
It does NOT change embeddings or the vector store structure.
Old chunks without IDs are migrated at retrieval time.

Architecture:
  Chunks (flat) → Doctrine Graph → Doctrinal Blocks (structured) → Reasoning
"""

import hashlib
import re
from utils.logger import get_logger
from typing import List, Dict, Optional
from collections import defaultdict

logger = get_logger(__name__)


# ============================================================
# HIERARCHICAL ID GENERATION
# ============================================================

def _normalize_for_hash(text: str) -> str:
    """Normalize text for consistent hashing."""
    if not text:
        return ""
    text = text.lower().strip()
    # Remove accents
    replacements = {
        "ç": "c", "ã": "a", "á": "a", "â": "a", "à": "a",
        "é": "e", "ê": "e", "í": "i", "ó": "o", "ô": "o",
        "ú": "u", "ü": "u",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    # Remove extra whitespace and punctuation
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _short_hash(text: str) -> str:
    """Generate a short deterministic hash (12 chars)."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]


def generate_author_id(author: str) -> str:
    """Generate stable author identifier."""
    normalized = _normalize_for_hash(author)
    if not normalized:
        return "author_unknown"
    return f"a_{_short_hash(normalized)}"


def generate_work_id(author: str, title: str, edition: str = "") -> str:
    """Generate stable work identifier (author + title + edition)."""
    combined = _normalize_for_hash(f"{author}|{title}|{edition}")
    return f"w_{_short_hash(combined)}"


def generate_chapter_id(work_id: str, chapter: str) -> str:
    """Generate stable chapter identifier."""
    if not chapter:
        return f"{work_id}_ch_none"
    combined = f"{work_id}|{_normalize_for_hash(chapter)}"
    return f"ch_{_short_hash(combined)}"


def generate_doctrine_id(author_id: str, legal_topic: str, chapter_id: str) -> str:
    """Generate stable doctrine identifier (author + topic + chapter)."""
    combined = f"{author_id}|{_normalize_for_hash(legal_topic)}|{chapter_id}"
    return f"d_{_short_hash(combined)}"


# ============================================================
# METADATA ENRICHMENT (for new chunks during indexing)
# ============================================================

def enrich_chunk_metadata(metadata: Dict) -> Dict:
    """Add hierarchical IDs to chunk metadata.

    Call this during indexing to add doctrine graph IDs.
    Non-destructive: preserves all existing metadata.

    Args:
        metadata: Existing chunk metadata dict

    Returns:
        Enriched metadata with author_id, work_id, chapter_id, doctrine_id
    """
    author = metadata.get("author", metadata.get("autor", ""))
    title = metadata.get("title", metadata.get("titulo", ""))
    edition = metadata.get("edition", metadata.get("edicao", ""))
    chapter = metadata.get("capitulo", metadata.get("chapter", ""))
    legal_area = metadata.get("legal_subject", metadata.get("materia", ""))

    author_id = generate_author_id(author)
    work_id = generate_work_id(author, title, edition)
    chapter_id = generate_chapter_id(work_id, chapter)
    doctrine_id = generate_doctrine_id(author_id, legal_area, chapter_id)

    metadata["author_id"] = author_id
    metadata["work_id"] = work_id
    metadata["chapter_id"] = chapter_id
    metadata["doctrine_id"] = doctrine_id

    return metadata


# ============================================================
# MIGRATION: compute IDs for old chunks at retrieval time
# ============================================================

def migrate_chunk(chunk: Dict) -> Dict:
    """Add hierarchical IDs to a retrieved chunk that lacks them.

    This ensures backward compatibility with old indexed chunks.
    IDs are computed from existing metadata fields.
    """
    meta = chunk.get("metadata", {})

    if "doctrine_id" in meta and meta["doctrine_id"]:
        return chunk  # Already has IDs

    # Compute from existing fields
    author = meta.get("author", meta.get("autor", ""))
    title = meta.get("title", meta.get("arquivo", ""))
    edition = meta.get("edition", meta.get("edicao", ""))
    chapter = meta.get("chapter", meta.get("capitulo", ""))
    legal_area = meta.get("legal_subject", meta.get("materia", ""))

    meta["author_id"] = generate_author_id(author)
    meta["work_id"] = generate_work_id(author, title, edition)
    meta["chapter_id"] = generate_chapter_id(meta["work_id"], chapter)
    meta["doctrine_id"] = generate_doctrine_id(meta["author_id"], legal_area, meta["chapter_id"])

    chunk["metadata"] = meta
    return chunk


# ============================================================
# DOCTRINAL BLOCK CONSTRUCTION
# ============================================================

class DoctrinalBlock:
    """A structured doctrinal unit: one author's position on a topic.

    Aggregates multiple chunks from the same doctrine_id into a single
    coherent block for the reasoning engine.
    """

    def __init__(self, doctrine_id: str):
        self.doctrine_id = doctrine_id
        self.author = ""
        self.author_id = ""
        self.work_title = ""
        self.work_id = ""
        self.year = 0
        self.edition = ""
        self.chapter = ""
        self.chapter_id = ""
        self.legal_area = ""
        self.pages = []
        self.chunks = []
        self.scores = []
        self.aggregated_score = 0.0

    def add_chunk(self, chunk: Dict):
        """Add a chunk to this doctrinal block."""
        meta = chunk.get("metadata", {})

        # Set block-level metadata from first chunk
        if not self.author:
            self.author = meta.get("author", "")
            self.author_id = meta.get("author_id", "")
            self.work_title = meta.get("title", "")
            self.work_id = meta.get("work_id", "")
            self.edition = meta.get("edition", "")
            self.chapter = meta.get("chapter", "")
            self.chapter_id = meta.get("chapter_id", "")
            self.legal_area = meta.get("legal_subject", "")

            year = meta.get("year", 0)
            try:
                self.year = int(year) if year else 0
            except (ValueError, TypeError):
                self.year = 0

        # Add page if present
        page = meta.get("page", "")
        if page and page not in self.pages:
            self.pages.append(page)

        # Add chunk text and score
        self.chunks.append(chunk["text"])
        self.scores.append(chunk.get("score", 0.0))

    def finalize(self):
        """Calculate aggregated score and sort pages."""
        if self.scores:
            # Aggregated score: weighted average favoring highest scores
            sorted_scores = sorted(self.scores, reverse=True)
            # Top score counts 50%, rest averaged
            if len(sorted_scores) == 1:
                self.aggregated_score = sorted_scores[0]
            else:
                top = sorted_scores[0]
                rest_avg = sum(sorted_scores[1:]) / len(sorted_scores[1:])
                self.aggregated_score = round(top * 0.5 + rest_avg * 0.5, 4)

        # Sort pages numerically
        try:
            self.pages.sort(key=lambda x: int(x) if str(x).isdigit() else 0)
        except (ValueError, TypeError):
            pass

    def to_context_string(self) -> str:
        """Convert to formatted string for LLM context."""
        parts = []
        parts.append(f"AUTOR: {self.author or 'Desconhecido'}")
        parts.append(f"OBRA: {self.work_title or 'Não identificada'} ({self.year or 's.d.'})")
        if self.edition:
            parts.append(f"EDIÇÃO: {self.edition}")
        if self.chapter:
            parts.append(f"CAPÍTULO: {self.chapter}")
        if self.pages:
            pages_str = ", ".join(str(p) for p in self.pages[:10])
            parts.append(f"PÁGINAS: {pages_str}")
        parts.append(f"RELEVÂNCIA AGREGADA: {self.aggregated_score:.2%}")
        parts.append(f"TRECHOS ({len(self.chunks)}):")

        for i, text in enumerate(self.chunks):
            parts.append(f"  [{i + 1}] {text}")

        return "\n".join(parts)

    def to_dict(self) -> Dict:
        """Convert to dict for API responses."""
        return {
            "doctrine_id": self.doctrine_id,
            "author": self.author,
            "author_id": self.author_id,
            "work_title": self.work_title,
            "work_id": self.work_id,
            "year": self.year,
            "edition": self.edition,
            "chapter": self.chapter,
            "legal_area": self.legal_area,
            "pages": self.pages,
            "chunk_count": len(self.chunks),
            "aggregated_score": self.aggregated_score,
        }


# ============================================================
# MAIN: GROUP CHUNKS INTO DOCTRINAL BLOCKS
# ============================================================

def build_doctrinal_blocks(chunks: List[Dict]) -> List[DoctrinalBlock]:
    """Transform flat chunks into structured doctrinal blocks.

    This is the core function of the Doctrine Graph Layer.

    1. Migrates old chunks (adds IDs if missing)
    2. Groups by doctrine_id
    3. Aggregates scores
    4. Returns sorted doctrinal blocks

    Args:
        chunks: Retrieved chunks from vector search

    Returns:
        Sorted list of DoctrinalBlock objects
    """
    if not chunks:
        return []

    # Step 1: Migrate old chunks
    migrated = [migrate_chunk(c) for c in chunks]

    # Step 2: Group by doctrine_id
    blocks_map: Dict[str, DoctrinalBlock] = {}

    for chunk in migrated:
        doctrine_id = chunk.get("metadata", {}).get("doctrine_id", "unknown")
        if doctrine_id not in blocks_map:
            blocks_map[doctrine_id] = DoctrinalBlock(doctrine_id)
        blocks_map[doctrine_id].add_chunk(chunk)

    # Step 3: Finalize and sort
    blocks = list(blocks_map.values())
    for block in blocks:
        block.finalize()

    # Sort by aggregated score (highest first)
    blocks.sort(key=lambda b: b.aggregated_score, reverse=True)

    logger.info(
        f"Doctrine Graph: {len(chunks)} chunks → {len(blocks)} doctrinal blocks "
        f"({len(set(b.author_id for b in blocks))} authors)"
    )

    return blocks


def build_structured_context(blocks: List[DoctrinalBlock]) -> str:
    """Build structured doctrinal context for the LLM.

    Instead of a flat list of chunks, the LLM receives organized
    doctrinal blocks grouped by author and work.

    Args:
        blocks: DoctrinalBlock objects from build_doctrinal_blocks()

    Returns:
        Formatted context string for LLM
    """
    if not blocks:
        return "Nenhuma fonte doutrinária relevante encontrada."

    parts = []
    parts.append("=" * 60)
    parts.append("FONTES DOUTRINÁRIAS ORGANIZADAS POR DOUTRINA")
    parts.append("=" * 60)

    # Group blocks by author for cleaner presentation
    by_author: Dict[str, List[DoctrinalBlock]] = defaultdict(list)
    for block in blocks:
        by_author[block.author or "Desconhecido"].append(block)

    for author, author_blocks in by_author.items():
        parts.append(f"\n{'─' * 50}")
        parts.append(f"AUTOR: {author}")
        parts.append(f"{'─' * 50}")

        for block in author_blocks:
            parts.append(f"\n{block.to_context_string()}")
            parts.append("")

    return "\n".join(parts)
