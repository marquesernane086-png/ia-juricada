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

VECTORDB_DIR = Path(__file__).parent.parent / "data" / "vectordb"


def set_db(database: AsyncIOMotorDatabase):
    """Set the database reference."""
    global db
    db = database


@router.post("/upload-package")
async def import_package(file: UploadFile = File(...)):
    """Import a pre-indexed package (ZIP) from the local indexing script.
    
    The ZIP should contain:
    - vectordb/ folder (ChromaDB data)
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
        
        logger.info(f"Received import package: {file.filename} ({len(content) / (1024*1024):.1f}MB)")
        
        # Extract to temp directory
        with tempfile.TemporaryDirectory() as extract_dir:
            with zipfile.ZipFile(tmp_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            extract_path = Path(extract_dir)
            
            # Find vectordb folder and metadata.json
            vectordb_src = None
            metadata_file = None
            
            # Search in extracted contents (might be in a subfolder)
            for item in extract_path.rglob("metadata.json"):
                metadata_file = item
                break
            
            for item in extract_path.rglob("vectordb"):
                if item.is_dir():
                    vectordb_src = item
                    break
            
            if not vectordb_src:
                raise HTTPException(status_code=400, detail="vectordb/ folder not found in ZIP")
            
            # Import metadata to MongoDB
            docs_imported = 0
            if metadata_file and metadata_file.exists():
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    documents = json.load(f)
                
                for doc in documents:
                    # Check if already exists
                    existing = await db.documents.find_one({"file_hash": doc.get("file_hash", "")})
                    if existing:
                        logger.info(f"Skipping duplicate: {doc.get('title', '?')}")
                        continue
                    
                    # Add required fields
                    doc.setdefault("legal_subject", "")
                    doc.setdefault("legal_institute", "")
                    doc.setdefault("file_path", "")
                    doc.setdefault("error_message", None)
                    doc.setdefault("created_at", datetime.now(timezone.utc).isoformat())
                    doc.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
                    
                    await db.documents.insert_one(doc)
                    docs_imported += 1
                
                logger.info(f"Imported {docs_imported} document records to MongoDB")
            
            # Replace ChromaDB data
            # We need to stop using the current collection, copy data, and reinitialize
            logger.info("Importing vector database...")
            
            # Copy ChromaDB files
            target_dir = VECTORDB_DIR
            
            # Merge: copy new files into existing vectordb
            for src_file in vectordb_src.rglob("*"):
                if src_file.is_file():
                    rel_path = src_file.relative_to(vectordb_src)
                    dest_file = target_dir / rel_path
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src_file), str(dest_file))
            
            logger.info(f"ChromaDB files copied to {target_dir}")
            
            # Reset the singleton so it reinitializes with new data
            vector_service._chroma_client = None
            vector_service._collection = None
            
            # Reinitialize and get count
            new_stats = vector_service.get_stats()
            
        # Clean up temp zip
        os.unlink(tmp_path)
        
        return {
            "message": "Import completed successfully",
            "documents_imported": docs_imported,
            "total_chunks": new_stats.get("total_chunks", 0),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Import error: {e}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.post("/metadata")
async def import_metadata_only(file: UploadFile = File(...)):
    """Import only metadata.json (for when vectordb is transferred separately)."""
    if not file.filename or not file.filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="Only JSON files are accepted")
    
    try:
        content = await file.read()
        documents = json.loads(content)
        
        docs_imported = 0
        for doc in documents:
            existing = await db.documents.find_one({"file_hash": doc.get("file_hash", "")})
            if existing:
                continue
            
            doc.setdefault("legal_subject", "")
            doc.setdefault("legal_institute", "")
            doc.setdefault("file_path", "")
            doc.setdefault("error_message", None)
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
