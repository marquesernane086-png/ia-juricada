"""Vector Service — Qdrant backend with LlamaIndex fallback.

Uses Qdrant for vector search when available.
Falls back to LlamaIndex default if Qdrant not initialized.
"""

import os
import re
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

_index = None
_embed_model = None
_qdrant_client = None
_using_qdrant = False
_rest_mode = False  # True when using REST API directly (ngrok workaround)

INDEX_DIR = str(Path(__file__).parent.parent / "data" / "indice")
QDRANT_DIR = str(Path(__file__).parent.parent / "data" / "qdrant_data")
QDRANT_DIR_ALT = "/tmp/qdrant_persistent"
QDRANT_REMOTE_URL = os.environ.get("QDRANT_URL", "")  # Remote Qdrant server
COLLECTION_NAME = "jurista_legal_docs"



def _create_rest_index():
    """Create a dummy index marker for REST mode."""
    global _rest_mode
    _rest_mode = True
    return "REST_MODE"


def _search_qdrant_rest(query: str, n_results: int = 10) -> list:
    """Search Qdrant via REST API (bypasses qdrant-client TLS issues)."""
    import requests as req
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(os.environ.get('EMBEDDING_MODEL', 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'))
    query_vector = model.encode(query, normalize_embeddings=True).tolist()

    headers = {"ngrok-skip-browser-warning": "true", "Content-Type": "application/json"}
    payload = {"query": query_vector, "limit": n_results, "with_payload": True}

    r = req.post(
        f"{QDRANT_REMOTE_URL}/collections/{COLLECTION_NAME}/points/query",
        json=payload, headers=headers, timeout=30
    )

    if r.status_code != 200:
        logger.error(f"Qdrant REST search failed: {r.status_code}")
        return []

    data = r.json()
    results = []
    for point in data.get("result", {}).get("points", []):
        payload = point.get("payload", {})
        score = point.get("score", 0.0)
        results.append({
            "text": payload.get("text", ""),
            "metadata": {k: v for k, v in payload.items() if k != "text"},
            "score": round(float(score), 4),
            "id": str(point.get("id", "")),
        })

    return results


def get_embed_model() -> HuggingFaceEmbedding:
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
    global _index, _qdrant_client, _using_qdrant

    if _index is not None:
        return _index

    get_embed_model()

    # Try Qdrant first - remote, then local
    try:
        from qdrant_client import QdrantClient
        from llama_index.vector_stores.qdrant import QdrantVectorStore

        # Priority 1: Remote Qdrant (ngrok/cloud) via REST API
        if QDRANT_REMOTE_URL:
            logger.info(f"Connecting to remote Qdrant: {QDRANT_REMOTE_URL}")
            try:
                import requests as req
                headers = {"ngrok-skip-browser-warning": "true"}
                r = req.get(f"{QDRANT_REMOTE_URL}/collections/{COLLECTION_NAME}", headers=headers, timeout=10)
                if r.status_code == 200:
                    pts = r.json().get("result", {}).get("points_count", 0)
                    logger.info(f"Remote Qdrant connected via REST! Points: {pts}")
                    _using_qdrant = True
                    _qdrant_client = None  # Using REST mode
                    # Create a minimal LlamaIndex wrapper — search uses REST directly
                    _index = _create_rest_index()
                    return _index
                else:
                    logger.warning(f"Remote Qdrant returned {r.status_code}")
            except Exception as e:
                logger.warning(f"Remote Qdrant REST failed: {e}. Falling back.")

        # Priority 2: Local Qdrant
        qdrant_path = None
        for path in [QDRANT_DIR, QDRANT_DIR_ALT]:
            if os.path.exists(path) and os.listdir(path):
                qdrant_path = path
                break

        if qdrant_path:
            logger.info(f"Loading Qdrant from: {qdrant_path}")
            _qdrant_client = QdrantClient(path=qdrant_path)
            vector_store = QdrantVectorStore(
                client=_qdrant_client,
                collection_name=COLLECTION_NAME,
            )
            storage_context = StorageContext.from_defaults(vector_store=vector_store)
            _index = VectorStoreIndex.from_documents([], storage_context=storage_context)
            _using_qdrant = True

            info = _qdrant_client.get_collection(COLLECTION_NAME)
            logger.info(f"Qdrant loaded. Points: {info.points_count}")
            return _index

    except ImportError:
        logger.info("qdrant-client not installed, using LlamaIndex fallback")
    except Exception as e:
        logger.warning(f"Qdrant init failed: {e}. Falling back to LlamaIndex.")

    # Fallback: LlamaIndex default
    os.makedirs(INDEX_DIR, exist_ok=True)
    docstore_path = os.path.join(INDEX_DIR, "docstore.json")

    if os.path.exists(docstore_path):
        try:
            logger.info(f"Loading LlamaIndex from: {INDEX_DIR}")
            storage_context = StorageContext.from_defaults(persist_dir=INDEX_DIR)
            _index = load_index_from_storage(storage_context)
            doc_count = len(_index.docstore.docs)
            logger.info(f"LlamaIndex loaded. Documents/chunks: {doc_count}")
            return _index
        except Exception as e:
            logger.warning(f"Could not load index: {e}")

    logger.info("Creating new empty index")
    _index = VectorStoreIndex.from_documents([], embed_model=get_embed_model())
    _index.storage_context.persist(persist_dir=INDEX_DIR)
    return _index


def add_document(text: str, metadata: Dict) -> int:
    index = get_index()
    if index is None:
        return 0

    clean_meta = {}
    for k, v in metadata.items():
        if v is None:
            clean_meta[k] = ""
        else:
            clean_meta[k] = v

    doc = Document(text=text, metadata=clean_meta)
    index.insert(doc)

    if not _using_qdrant:
        index.storage_context.persist(persist_dir=INDEX_DIR)

    logger.info(f"Document added: {clean_meta.get('arquivo', 'unknown')}")
    return 1


def search(query: str, n_results: int = 10, where_filter: Optional[Dict] = None) -> List[Dict]:
    index = get_index()
    if index is None:
        logger.warning("Index not available.")
        return []

    # Check if empty
    if _using_qdrant and _qdrant_client:
        try:
            info = _qdrant_client.get_collection(COLLECTION_NAME)
            if info.points_count == 0:
                logger.warning("Qdrant collection is empty.")
                return []
        except Exception:
            pass
    elif not _using_qdrant:
        if len(index.docstore.docs) == 0:
            logger.warning("Index is empty.")
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

        # Extract author/title from combined fields
        author = meta.get("author", meta.get("autor", ""))
        title = meta.get("title", meta.get("arquivo", ""))
        year = meta.get("year", meta.get("ano", ""))

        # Parse "Author, Year. Title" format
        if not author and title:
            match = re.match(r'^([^,]+),\s*(\d{4})\.\s*(.+)$', title)
            if match:
                author = match.group(1).strip()
                if not year:
                    year = int(match.group(2))
                title = match.group(3).strip()

        formatted.append({
            "text": node.get_text(),
            "metadata": {
                "doc_id": meta.get("doc_id", meta.get("hash", "")),
                "author": author,
                "title": title,
                "year": year,
                "edition": meta.get("edition", meta.get("edicao", "")),
                "legal_subject": meta.get("legal_subject", meta.get("materia", "")),
                "legal_institute": meta.get("legal_institute", ""),
                "page": meta.get("page", meta.get("pagina", "")),
                "chapter": meta.get("capitulo", meta.get("chapter", "")),
                "author_id": meta.get("author_id", ""),
                "work_id": meta.get("work_id", ""),
                "chapter_id": meta.get("chapter_id", ""),
                "doctrine_id": meta.get("doctrine_id", ""),
                "fonte_normativa": meta.get("fonte_normativa", ""),
                "orgao_julgador": meta.get("orgao_julgador", ""),
                "peso_normativo": meta.get("peso_normativo", 0),
                "posicao_doutrinaria": meta.get("posicao_doutrinaria", ""),
            },
            "score": round(float(score), 4),
            "id": node.node_id or "",
        })

    logger.info(f"Search returned {len(formatted)} results for: {query[:80]}...")
    return formatted


def delete_document_chunks(doc_id: str) -> int:
    # TODO: implement for Qdrant
    return 0


def import_index(source_dir: str) -> int:
    """Import pre-built index (LlamaIndex or Qdrant)."""
    global _index, _qdrant_client, _using_qdrant

    get_embed_model()

    # Check if source has Qdrant data
    qdrant_source = None
    for item in Path(source_dir).rglob("collection"):
        if item.is_dir():
            qdrant_source = item.parent
            break

    if qdrant_source:
        # Import Qdrant data
        logger.info(f"Importing Qdrant data from {qdrant_source}")
        os.makedirs(QDRANT_DIR, exist_ok=True)
        for item in qdrant_source.iterdir():
            dest = Path(QDRANT_DIR) / item.name
            if item.is_file():
                shutil.copy2(str(item), str(dest))
            elif item.is_dir():
                if dest.exists():
                    shutil.rmtree(str(dest))
                shutil.copytree(str(item), str(dest))

        _index = None
        _qdrant_client = None
        _using_qdrant = False
        index = get_index()
        return get_stats().get("total_chunks", 0)

    # Fallback: LlamaIndex import
    docstore_path = os.path.join(source_dir, "docstore.json")
    if os.path.exists(docstore_path):
        logger.info(f"Importing LlamaIndex data from {source_dir}")
        os.makedirs(INDEX_DIR, exist_ok=True)
        for item in Path(source_dir).iterdir():
            dest = Path(INDEX_DIR) / item.name
            if item.is_file():
                shutil.copy2(str(item), str(dest))
            elif item.is_dir():
                if dest.exists():
                    shutil.rmtree(str(dest))
                shutil.copytree(str(item), str(dest))

        _index = None
        index = get_index()
        count = len(index.docstore.docs) if index else 0
        logger.info(f"Imported {count} documents")
        return count

    raise ValueError("No recognizable index found in source directory")


def get_stats() -> Dict:
    index = get_index()

    if _using_qdrant and _qdrant_client:
        try:
            info = _qdrant_client.get_collection(COLLECTION_NAME)
            return {
                "total_chunks": info.points_count,
                "backend": "qdrant",
                "index_dir": QDRANT_DIR,
            }
        except Exception:
            pass

    if index:
        try:
            count = len(index.docstore.docs)
        except Exception:
            count = 0
        return {
            "total_chunks": count,
            "backend": "llamaindex",
            "index_dir": INDEX_DIR,
        }

    return {"total_chunks": 0, "backend": "none"}


def reset_index():
    global _index, _qdrant_client, _using_qdrant
    _index = None
    _qdrant_client = None
    _using_qdrant = False
