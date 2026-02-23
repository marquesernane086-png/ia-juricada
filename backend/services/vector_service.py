"""Vector Service - Manages embeddings and ChromaDB storage."""

import os
import logging
from typing import List, Dict, Optional
from pathlib import Path

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Singleton instances
_embedding_model = None
_chroma_client = None
_collection = None

COLLECTION_NAME = "jurista_legal_docs"


def get_embedding_model() -> SentenceTransformer:
    """Get or initialize the embedding model (singleton)."""
    global _embedding_model
    if _embedding_model is None:
        model_name = os.environ.get(
            'EMBEDDING_MODEL',
            'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
        )
        logger.info(f"Loading embedding model: {model_name}")
        _embedding_model = SentenceTransformer(model_name)
        logger.info(f"Embedding model loaded. Dimension: {_embedding_model.get_sentence_embedding_dimension()}")
    return _embedding_model


def get_chroma_client() -> chromadb.ClientAPI:
    """Get or initialize the ChromaDB client (singleton)."""
    global _chroma_client
    if _chroma_client is None:
        persist_dir = str(Path(__file__).parent.parent / "data" / "vectordb")
        os.makedirs(persist_dir, exist_ok=True)
        logger.info(f"Initializing ChromaDB at: {persist_dir}")
        _chroma_client = chromadb.PersistentClient(path=persist_dir)
    return _chroma_client


def get_collection() -> chromadb.Collection:
    """Get or create the main document collection."""
    global _collection
    if _collection is None:
        client = get_chroma_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"ChromaDB collection '{COLLECTION_NAME}' ready. Count: {_collection.count()}")
    return _collection


def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for a list of texts."""
    model = get_embedding_model()
    embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    return embeddings.tolist()


def index_chunks(chunks: List[Dict]) -> int:
    """Index document chunks into ChromaDB.
    
    Args:
        chunks: List of chunk dicts with 'text' and 'metadata' keys
    
    Returns:
        Number of chunks indexed
    """
    if not chunks:
        return 0
    
    collection = get_collection()
    
    texts = [c["text"] for c in chunks]
    metadatas = []
    ids = []
    
    for i, chunk in enumerate(chunks):
        meta = chunk["metadata"].copy()
        # ChromaDB requires string/int/float/bool values in metadata
        # Convert None values to empty strings
        for key, value in meta.items():
            if value is None:
                meta[key] = ""
        metadatas.append(meta)
        
        doc_id = meta.get("doc_id", "unknown")
        chunk_idx = meta.get("chunk_index", i)
        ids.append(f"{doc_id}_chunk_{chunk_idx}")
    
    # Generate embeddings
    logger.info(f"Generating embeddings for {len(texts)} chunks...")
    embeddings = generate_embeddings(texts)
    
    # Add to ChromaDB in batches
    batch_size = 100
    total_added = 0
    
    for start in range(0, len(texts), batch_size):
        end = min(start + batch_size, len(texts))
        collection.upsert(
            ids=ids[start:end],
            documents=texts[start:end],
            embeddings=embeddings[start:end],
            metadatas=metadatas[start:end]
        )
        total_added += (end - start)
        logger.info(f"Indexed batch {start}-{end} ({total_added}/{len(texts)})")
    
    logger.info(f"Total chunks in collection: {collection.count()}")
    return total_added


def search(
    query: str,
    n_results: int = 10,
    where_filter: Optional[Dict] = None
) -> List[Dict]:
    """Search for relevant chunks using semantic similarity.
    
    Args:
        query: Search query text
        n_results: Number of results to return
        where_filter: Optional metadata filter
    
    Returns:
        List of result dicts with text, metadata, and score
    """
    collection = get_collection()
    
    if collection.count() == 0:
        logger.warning("Vector store is empty. No documents indexed yet.")
        return []
    
    # Generate query embedding
    query_embedding = generate_embeddings([query])[0]
    
    # Build search params
    search_params = {
        "query_embeddings": [query_embedding],
        "n_results": min(n_results, collection.count()),
    }
    
    if where_filter:
        search_params["where"] = where_filter
    
    results = collection.query(**search_params)
    
    # Format results
    formatted = []
    if results and results['documents'] and results['documents'][0]:
        for i in range(len(results['documents'][0])):
            distance = results['distances'][0][i] if results.get('distances') else 0
            # ChromaDB cosine distance: 0 = identical, 2 = opposite
            # Convert to similarity score: 1 - (distance/2)
            similarity = 1.0 - (distance / 2.0)
            
            formatted.append({
                "text": results['documents'][0][i],
                "metadata": results['metadatas'][0][i] if results.get('metadatas') else {},
                "score": round(similarity, 4),
                "id": results['ids'][0][i] if results.get('ids') else ""
            })
    
    logger.info(f"Search returned {len(formatted)} results for query: {query[:80]}...")
    return formatted


def delete_document_chunks(doc_id: str) -> int:
    """Delete all chunks for a document from the vector store."""
    collection = get_collection()
    
    # Get all chunk IDs for this document
    try:
        results = collection.get(
            where={"doc_id": doc_id}
        )
        if results and results['ids']:
            collection.delete(ids=results['ids'])
            logger.info(f"Deleted {len(results['ids'])} chunks for doc {doc_id}")
            return len(results['ids'])
    except Exception as e:
        logger.error(f"Error deleting chunks for doc {doc_id}: {e}")
    
    return 0


def get_stats() -> Dict:
    """Get vector store statistics."""
    collection = get_collection()
    return {
        "total_chunks": collection.count(),
        "collection_name": COLLECTION_NAME,
    }
