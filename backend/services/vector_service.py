"""Vector Service - Manages LlamaIndex storage and retrieval.

Compatible with the local indexing script (indexar_acervo.py) format.
Uses LlamaIndex VectorStoreIndex for persistent storage.
"""

import os
import logging
import shutil
from typing import List, Dict, Optional
from pathlib import Path

from llama_index.core import (
    VectorStoreIndex,
    Document,
    StorageContext,
    Settings,
    load_index_from_storage,
)
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

logger = logging.getLogger(__name__)

# Singleton
_index = None
_embed_model = None

INDEX_DIR = str(Path(__file__).parent.parent / "data" / "indice")


def get_embed_model() -> HuggingFaceEmbedding:
    """Get or initialize the embedding model (singleton)."""
    global _embed_model
    if _embed_model is None:
        model_name = os.environ.get(
            'EMBEDDING_MODEL',
            'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
        )
        logger.info(f"Loading embedding model: {model_name}")
        _embed_model = HuggingFaceEmbedding(model_name=model_name)
        Settings.embed_model = _embed_model
        logger.info("Embedding model loaded")
    return _embed_model


def get_index() -> Optional[VectorStoreIndex]:
    """Get or load the VectorStoreIndex (singleton)."""
    global _index

    if _index is not None:
        return _index

    # Ensure embed model is loaded
    get_embed_model()

    os.makedirs(INDEX_DIR, exist_ok=True)

    # Try to load existing index
    docstore_path = os.path.join(INDEX_DIR, "docstore.json")
    if os.path.exists(docstore_path):
        try:
            logger.info(f"Loading existing index from: {INDEX_DIR}")
            storage_context = StorageContext.from_defaults(persist_dir=INDEX_DIR)
            _index = load_index_from_storage(storage_context)
            doc_count = len(_index.docstore.docs)
            logger.info(f"Index loaded. Documents/chunks: {doc_count}")
            return _index
        except Exception as e:
            logger.warning(f"Could not load index: {e}. Will create new one.")

    # Create empty index
    logger.info("Creating new empty index")
    _index = VectorStoreIndex.from_documents([], embed_model=get_embed_model())
    _index.storage_context.persist(persist_dir=INDEX_DIR)
    return _index


def add_document(text: str, metadata: Dict) -> int:
    """Add a single document to the index.

    LlamaIndex will handle chunking automatically.

    Args:
        text: Full document text
        metadata: Document metadata dict

    Returns:
        Number of nodes created
    """
    index = get_index()
    if index is None:
        return 0

    # Clean metadata values - LlamaIndex needs string-compatible values
    clean_meta = {}
    for k, v in metadata.items():
        if v is None:
            clean_meta[k] = ""
        else:
            clean_meta[k] = v

    doc = Document(text=text, metadata=clean_meta)

    # Insert into index
    index.insert(doc)
    index.storage_context.persist(persist_dir=INDEX_DIR)

    logger.info(f"Document added: {clean_meta.get('arquivo', 'unknown')}")
    return 1


def search(query: str, n_results: int = 10, where_filter: Optional[Dict] = None) -> List[Dict]:
    """Search for relevant chunks using the index.

    Args:
        query: Search query text
        n_results: Number of results to return
        where_filter: Optional metadata filter (not fully supported in simple mode)

    Returns:
        List of result dicts with text, metadata, and score
    """
    index = get_index()
    if index is None or len(index.docstore.docs) == 0:
        logger.warning("Index is empty. No documents indexed yet.")
        return []

    try:
        retriever = index.as_retriever(similarity_top_k=n_results)
        nodes = retriever.retrieve(query)
    except Exception as e:
        logger.error(f"Search error: {e}")
        return []

    formatted = []
    for node in nodes:
        meta = node.metadata or {}
        score = node.score if node.score is not None else 0.0

        formatted.append({
            "text": node.get_text(),
            "metadata": {
                "doc_id": meta.get("doc_id", meta.get("hash", "")),
                "author": meta.get("author", meta.get("autor", "")),
                "title": meta.get("title", meta.get("arquivo", "")),
                "year": meta.get("year", meta.get("ano", "")),
                "edition": meta.get("edition", meta.get("edicao", "")),
                "legal_subject": meta.get("legal_subject", meta.get("materia", "")),
                "legal_institute": meta.get("legal_institute", ""),
                "page": meta.get("page", ""),
            },
            "score": round(float(score), 4),
            "id": node.node_id or "",
        })

    logger.info(f"Search returned {len(formatted)} results for: {query[:80]}...")
    return formatted


def delete_document_chunks(doc_id: str) -> int:
    """Delete all chunks for a document from the index."""
    index = get_index()
    if index is None:
        return 0

    deleted = 0
    try:
        docs_to_delete = []
        for node_id, node in index.docstore.docs.items():
            meta = node.metadata or {}
            if meta.get("hash") == doc_id or meta.get("doc_id") == doc_id:
                docs_to_delete.append(node_id)

        for node_id in docs_to_delete:
            index.delete_ref_doc(node_id, delete_from_docstore=True)
            deleted += 1

        if deleted > 0:
            index.storage_context.persist(persist_dir=INDEX_DIR)
            logger.info(f"Deleted {deleted} nodes for doc {doc_id}")
    except Exception as e:
        logger.error(f"Error deleting doc chunks: {e}")

    return deleted


def import_index(source_dir: str) -> int:
    """Import a pre-built LlamaIndex index from a directory.

    This replaces the current index with the imported one,
    or merges if there's already data.

    Args:
        source_dir: Path to the LlamaIndex persist directory

    Returns:
        Number of documents in the new index
    """
    global _index

    get_embed_model()

    docstore_path = os.path.join(source_dir, "docstore.json")
    if not os.path.exists(docstore_path):
        raise ValueError(f"No docstore.json found in {source_dir}")

    # If no existing index, just copy the new one
    existing_docstore = os.path.join(INDEX_DIR, "docstore.json")
    if not os.path.exists(existing_docstore):
        logger.info(f"No existing index. Copying imported index to {INDEX_DIR}")
        os.makedirs(INDEX_DIR, exist_ok=True)
        for item in Path(source_dir).iterdir():
            dest = Path(INDEX_DIR) / item.name
            if item.is_file():
                shutil.copy2(str(item), str(dest))
            elif item.is_dir():
                if dest.exists():
                    shutil.rmtree(str(dest))
                shutil.copytree(str(item), str(dest))

        # Reset singleton to reload
        _index = None
        index = get_index()
        count = len(index.docstore.docs) if index else 0
        logger.info(f"Imported index with {count} documents")
        return count

    # If existing index, merge
    logger.info("Merging imported index with existing index")

    # Load the imported index
    imported_storage = StorageContext.from_defaults(persist_dir=source_dir)
    imported_index = load_index_from_storage(imported_storage)

    # Get current index
    current_index = get_index()

    # Insert all documents from imported into current
    count = 0
    for node_id, node in imported_index.docstore.docs.items():
        try:
            doc = Document(text=node.get_content(), metadata=node.metadata or {})
            current_index.insert(doc)
            count += 1
        except Exception as e:
            logger.warning(f"Could not import node {node_id}: {e}")

    current_index.storage_context.persist(persist_dir=INDEX_DIR)
    _index = current_index
    logger.info(f"Merged {count} documents into existing index")
    return count


def get_stats() -> Dict:
    """Get index statistics."""
    index = get_index()
    if index is None:
        return {"total_chunks": 0, "index_dir": INDEX_DIR}

    try:
        count = len(index.docstore.docs)
    except Exception:
        count = 0

    return {
        "total_chunks": count,
        "index_dir": INDEX_DIR,
    }


def reset_index():
    """Reset the singleton (useful after import)."""
    global _index
    _index = None
