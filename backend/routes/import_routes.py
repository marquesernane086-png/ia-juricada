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

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from motor.motor_asyncio import AsyncIOMotorDatabase

from services import vector_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/import", tags=["import"])

db: Optional[AsyncIOMotorDatabase] = None

UPLOAD_DIR = Path(__file__).parent.parent / "data" / "uploads"


def set_db(database: AsyncIOMotorDatabase):
    global db
    db = database


async def _process_import(zip_path: str):
    """Background task to process the import."""
    try:
        logger.info(f"Starting background import of {zip_path}")

        with tempfile.TemporaryDirectory() as extract_dir:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            extract_path = Path(extract_dir)

            # Find docstore.json
            index_src = None
            for item in extract_path.rglob("docstore.json"):
                index_src = item.parent
                break

            if not index_src:
                logger.error("No docstore.json found in ZIP")
                return

            logger.info(f"Found index at: {index_src}")

            # Import the index (direct copy, fast)
            doc_count = vector_service.import_index(str(index_src))
            logger.info(f"Index imported: {doc_count} documents")

            # Import metadata from controle_index.json
            for controle_file in extract_path.rglob("controle_index.json"):
                with open(controle_file, 'r', encoding='utf-8') as f:
                    controle = json.load(f)

                docs_imported = 0
                for file_hash, info in controle.items():
                    existing = await db.documents.find_one({"file_hash": file_hash})
                    if existing:
                        continue

                    doc_record = {
                        "id": file_hash[:36],
                        "title": info.get("arquivo", "").replace(".pdf", "").replace(".epub", ""),
                        "author": info.get("autor", ""),
                        "year": info.get("ano"),
                        "edition": info.get("edicao", ""),
                        "legal_subject": info.get("materia", ""),
                        "legal_institute": "",
                        "file_path": "",
                        "file_name": info.get("arquivo", ""),
                        "file_hash": file_hash,
                        "file_type": info.get("arquivo", "").split(".")[-1] if info.get("arquivo") else "",
                        "file_size": 0,
                        "total_pages": info.get("paginas"),
                        "total_chunks": 0,
                        "status": "indexed",
                        "error_message": None,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                    await db.documents.insert_one(doc_record)
                    docs_imported += 1

                logger.info(f"Imported {docs_imported} records from controle_index.json")
                break

            # Try metadata.json too
            for metadata_file in extract_path.rglob("metadata.json"):
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
                    doc_info.setdefault("status", "indexed")
                    doc_info.setdefault("created_at", datetime.now(timezone.utc).isoformat())
                    doc_info.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
                    await db.documents.insert_one(doc_info)
                break

        # Clean up ZIP
        os.unlink(zip_path)
        logger.info("Import completed successfully!")

    except Exception as e:
        logger.error(f"Background import error: {e}")
        try:
            os.unlink(zip_path)
        except OSError:
            pass


@router.post("/upload-package")
async def import_package(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Upload ZIP and import in background. Returns immediately."""
    if not file.filename or not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Only ZIP files are accepted")

    # Save ZIP to uploads dir
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = UPLOAD_DIR / f"import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

    content = await file.read()
    with open(zip_path, "wb") as f:
        f.write(content)

    size_mb = len(content) / (1024 * 1024)
    logger.info(f"Received {file.filename} ({size_mb:.1f}MB), starting background import")

    # Run import in background
    background_tasks.add_task(_process_import, str(zip_path))

    return {
        "message": f"ZIP recebido ({size_mb:.1f}MB). Importação iniciada em background. Aguarde alguns segundos e atualize a página.",
        "status": "processing",
        "file_size_mb": round(size_mb, 1),
    }
