"""Import routes - Import pre-indexed data from local indexing script."""

import os
import json
import shutil
import logging
import zipfile
import tempfile
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, UploadFile, File, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from services import vector_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/import", tags=["import"])

# Will be set from server.py
db: Optional[AsyncIOMotorDatabase] = None


def set_db(database: AsyncIOMotorDatabase):
    """Set the database reference."""
    global db
    db = database


@router.post("/upload-package")
async def import_package(file: UploadFile = File(...)):
    """Import a pre-indexed package (ZIP) from the local indexing script.

    The ZIP should contain:
    - indice/ folder (LlamaIndex persist data with docstore.json)
    - OR: vectordb/ folder (ChromaDB data) + metadata.json

    Optionally:
    - controle_index.json (document metadata)
    - metadata.json (document metadata)
    """
    if not file.filename or not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Only ZIP files are accepted")

    try:
        # Save uploaded ZIP to temp location
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        logger.info(f"Received import package: {file.filename} ({len(content) / (1024 * 1024):.1f}MB)")

        # Extract to temp directory
        with tempfile.TemporaryDirectory() as extract_dir:
            with zipfile.ZipFile(tmp_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            extract_path = Path(extract_dir)

            # Find the index directory (look for docstore.json)
            index_src = None
            for item in extract_path.rglob("docstore.json"):
                index_src = item.parent
                break

            if not index_src:
                raise HTTPException(
                    status_code=400,
                    detail="No LlamaIndex index found in ZIP (missing docstore.json)"
                )

            logger.info(f"Found index at: {index_src}")

            # Import the index
            doc_count = vector_service.import_index(str(index_src))

            # Import metadata to MongoDB
            docs_imported = 0

            # Try controle_index.json (format from user's script)
            controle_file = None
            for item in extract_path.rglob("controle_index.json"):
                controle_file = item
                break

            if controle_file and controle_file.exists():
                with open(controle_file, 'r', encoding='utf-8') as f:
                    controle = json.load(f)

                for file_hash, info in controle.items():
                    existing = await db.documents.find_one({"file_hash": file_hash})
                    if existing:
                        continue

                    doc_record = {
                        "id": file_hash[:36],  # Use hash prefix as ID
                        "title": info.get("arquivo", "").replace(".pdf", "").replace(".epub", ""),
                        "author": info.get("autor", ""),
                        "year": info.get("ano"),
                        "edition": "",
                        "legal_subject": info.get("materia", ""),
                        "legal_institute": "",
                        "file_path": "",
                        "file_name": info.get("arquivo", ""),
                        "file_hash": file_hash,
                        "file_type": info.get("arquivo", "").split(".")[-1] if info.get("arquivo") else "",
                        "file_size": 0,
                        "total_pages": None,
                        "total_chunks": 0,
                        "status": "indexed",
                        "error_message": None,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                    await db.documents.insert_one(doc_record)
                    docs_imported += 1

                logger.info(f"Imported {docs_imported} document records from controle_index.json")

            # Try metadata.json (alternative format)
            metadata_file = None
            for item in extract_path.rglob("metadata.json"):
                metadata_file = item
                break

            if metadata_file and metadata_file.exists():
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    documents = json.load(f)

                for doc_info in documents:
                    fh = doc_info.get("file_hash", doc_info.get("hash", ""))
                    if not fh:
                        continue
                    existing = await db.documents.find_one({"file_hash": fh})
                    if existing:
                        continue

                    doc_info.setdefault("id", fh[:36])
                    doc_info.setdefault("legal_subject", doc_info.get("materia", ""))
                    doc_info.setdefault("legal_institute", "")
                    doc_info.setdefault("file_path", "")
                    doc_info.setdefault("error_message", None)
                    doc_info.setdefault("status", "indexed")
                    doc_info.setdefault("file_hash", fh)
                    doc_info.setdefault("created_at", datetime.now(timezone.utc).isoformat())
                    doc_info.setdefault("updated_at", datetime.now(timezone.utc).isoformat())

                    await db.documents.insert_one(doc_info)
                    docs_imported += 1

                logger.info(f"Imported {docs_imported} document records from metadata.json")

        # Clean up temp zip
        os.unlink(tmp_path)

        stats = vector_service.get_stats()

        return {
            "message": "Import completed successfully",
            "documents_imported": docs_imported,
            "index_documents": doc_count,
            "total_chunks": stats.get("total_chunks", 0),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Import error: {e}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.post("/metadata")
async def import_metadata_only(file: UploadFile = File(...)):
    """Import only metadata (controle_index.json or metadata.json)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    try:
        content = await file.read()
        data = json.loads(content)

        docs_imported = 0

        # Detect format: dict (controle_index.json) or list (metadata.json)
        if isinstance(data, dict):
            for file_hash, info in data.items():
                existing = await db.documents.find_one({"file_hash": file_hash})
                if existing:
                    continue
                doc_record = {
                    "id": file_hash[:36],
                    "title": info.get("arquivo", ""),
                    "author": info.get("autor", ""),
                    "year": info.get("ano"),
                    "legal_subject": info.get("materia", ""),
                    "legal_institute": "",
                    "file_path": "",
                    "file_name": info.get("arquivo", ""),
                    "file_hash": file_hash,
                    "file_type": "",
                    "file_size": 0,
                    "total_chunks": 0,
                    "status": "indexed",
                    "error_message": None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                await db.documents.insert_one(doc_record)
                docs_imported += 1
        elif isinstance(data, list):
            for doc in data:
                fh = doc.get("file_hash", doc.get("hash", ""))
                if not fh:
                    continue
                existing = await db.documents.find_one({"file_hash": fh})
                if existing:
                    continue
                doc.setdefault("status", "indexed")
                doc.setdefault("created_at", datetime.now(timezone.utc).isoformat())
                doc.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
                await db.documents.insert_one(doc)
                docs_imported += 1

        return {
            "message": f"Imported {docs_imported} document records",
            "documents_imported": docs_imported
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
