"""Document management routes - Upload, list, delete documents."""

import os
import hashlib
import logging
import asyncio
import re
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from motor.motor_asyncio import AsyncIOMotorDatabase

from models.schemas import (
    DocumentMetadata, DocumentUploadResponse, DocumentListResponse,
    DocumentUpdateRequest
)
from services import ingestion_service, indexing_service, vector_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

# Will be set from server.py
db: Optional[AsyncIOMotorDatabase] = None

UPLOAD_DIR = Path(__file__).parent.parent / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def set_db(database: AsyncIOMotorDatabase):
    """Set the database reference."""
    global db
    db = database


async def _process_document(doc_id: str, file_path: str, file_name: str):
    """Background task to process and index a document."""
    try:
        logger.info(f"Processing document: {file_name} (ID: {doc_id})")
        
        # Update status to processing
        await db.documents.update_one(
            {"id": doc_id},
            {"$set": {"status": "processing", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        
        # Step 1: Extract text and metadata
        full_text, extracted_meta = ingestion_service.extract_text(file_path)
        
        if not full_text.strip():
            raise ValueError("No text could be extracted from the document.")
        
        # Update document with extracted metadata
        update_fields = {"updated_at": datetime.now(timezone.utc).isoformat()}
        if extracted_meta.get("title"):
            update_fields["title"] = extracted_meta["title"]
        if extracted_meta.get("author"):
            update_fields["author"] = extracted_meta["author"]
        if extracted_meta.get("year"):
            update_fields["year"] = extracted_meta["year"]
        if extracted_meta.get("total_pages"):
            update_fields["total_pages"] = extracted_meta["total_pages"]
        
        await db.documents.update_one({"id": doc_id}, {"$set": update_fields})
        
        # Step 2: Get current document metadata
        doc = await db.documents.find_one({"id": doc_id}, {"_id": 0})
        
        doc_metadata = {
            "doc_id": doc_id,
            "autor": doc.get("author", ""),
            "author": doc.get("author", ""),
            "arquivo": file_name,
            "title": doc.get("title", file_name),
            "ano": doc.get("year", 0),
            "year": doc.get("year", 0),
            "edition": doc.get("edition", ""),
            "materia": doc.get("legal_subject", ""),
            "legal_subject": doc.get("legal_subject", ""),
            "legal_institute": doc.get("legal_institute", ""),
            "hash": doc.get("file_hash", ""),
            "caminho": str(file_path),
        }
        
        # Step 3: Add to LlamaIndex (handles chunking + embedding automatically)
        indexed_count = vector_service.add_document(full_text, doc_metadata)
        
        # Step 4: Update document status
        await db.documents.update_one(
            {"id": doc_id},
            {"$set": {
                "status": "indexed",
                "total_chunks": indexed_count,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        logger.info(f"Document indexed successfully: {file_name} ({indexed_count} chunks)")
        
    except Exception as e:
        logger.error(f"Error processing document {doc_id}: {e}")
        try:
            await db.documents.update_one(
                {"id": doc_id},
                {"$set": {
                    "status": "error",
                    "error_message": str(e),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
        except Exception:
            pass


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    year: Optional[int] = Form(None),
    edition: Optional[str] = Form(None),
    legal_subject: Optional[str] = Form(None),
    legal_institute: Optional[str] = Form(None),
):
    """Upload a legal document (PDF or EPUB) for indexing."""
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    ext = Path(file.filename).suffix.lower()
    if ext not in ['.pdf', '.epub']:
        raise HTTPException(status_code=400, detail="Only PDF and EPUB files are supported")
    
    # Read and validate size (max 200MB)
    content = await file.read()
    MAX_SIZE = 200 * 1024 * 1024  # 200MB
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large. Max: {MAX_SIZE/(1024*1024):.0f}MB")
    
    # Sanitize filename (prevent path traversal)
    safe_filename = Path(file.filename).name  # strips any ../ or path components
    safe_filename = re.sub(r'[^\w\s\-\.\(\)]', '_', safe_filename)  # remove special chars
    
    # Save file
    file_path = UPLOAD_DIR / safe_filename
    with open(file_path, "wb") as f:
        f.write(content)
    
    # Compute hash for deduplication
    file_hash = ingestion_service.compute_file_hash(str(file_path))
    
    # Check for duplicate
    existing = await db.documents.find_one({"file_hash": file_hash, "status": "indexed"}, {"_id": 0})
    if existing:
        os.remove(file_path)
        return DocumentUploadResponse(
            id=existing["id"],
            file_name=file.filename,
            status="duplicate",
            message=f"Document already indexed as '{existing.get('title', file.filename)}'"
        )
    
    # Try to guess metadata from filename
    filename_meta = ingestion_service.guess_metadata_from_filename(file.filename)
    
    # Create document metadata
    doc = DocumentMetadata(
        title=title or filename_meta.get("title", Path(file.filename).stem),
        author=author or filename_meta.get("author", ""),
        year=year or filename_meta.get("year"),
        edition=edition or "",
        legal_subject=legal_subject or "",
        legal_institute=legal_institute or "",
        file_path=str(file_path),
        file_name=file.filename,
        file_hash=file_hash,
        file_type=ext.replace(".", ""),
        file_size=len(content),
        status="pending"
    )
    
    # Save to MongoDB
    doc_dict = doc.model_dump()
    doc_dict['created_at'] = doc_dict['created_at'].isoformat()
    doc_dict['updated_at'] = doc_dict['updated_at'].isoformat()
    await db.documents.insert_one(doc_dict)
    
    # Start background processing
    background_tasks.add_task(_process_document, doc.id, str(file_path), file.filename)
    
    return DocumentUploadResponse(
        id=doc.id,
        file_name=file.filename,
        status="processing",
        message="Document uploaded and processing started"
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents():
    """List all documents."""
    docs = await db.documents.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    
    # Parse datetime strings
    for doc in docs:
        for field in ['created_at', 'updated_at']:
            if isinstance(doc.get(field), str):
                try:
                    doc[field] = datetime.fromisoformat(doc[field])
                except (ValueError, TypeError):
                    doc[field] = datetime.now(timezone.utc)
    
    return DocumentListResponse(
        documents=[DocumentMetadata(**doc) for doc in docs],
        total=len(docs)
    )


@router.get("/{doc_id}")
async def get_document(doc_id: str):
    """Get document details."""
    doc = await db.documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    for field in ['created_at', 'updated_at']:
        if isinstance(doc.get(field), str):
            try:
                doc[field] = datetime.fromisoformat(doc[field])
            except (ValueError, TypeError):
                doc[field] = datetime.now(timezone.utc)
    
    return DocumentMetadata(**doc)


@router.patch("/{doc_id}")
async def update_document(doc_id: str, update: DocumentUpdateRequest):
    """Update document metadata."""
    doc = await db.documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if update_data:
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.documents.update_one({"id": doc_id}, {"$set": update_data})
    
    return {"message": "Document updated", "updated_fields": list(update_data.keys())}


@router.delete("/{doc_id}")
async def delete_document(doc_id: str):
    """Delete a document and its chunks from the vector store."""
    doc = await db.documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Delete from vector store
    deleted_chunks = vector_service.delete_document_chunks(doc_id)
    
    # Delete file
    try:
        if os.path.exists(doc.get("file_path", "")):
            os.remove(doc["file_path"])
    except Exception as e:
        logger.warning(f"Could not delete file: {e}")
    
    # Delete from MongoDB
    await db.documents.delete_one({"id": doc_id})
    
    return {
        "message": "Document deleted",
        "deleted_chunks": deleted_chunks
    }


@router.post("/{doc_id}/reindex")
async def reindex_document(doc_id: str, background_tasks: BackgroundTasks):
    """Reindex a document."""
    doc = await db.documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if not os.path.exists(doc.get("file_path", "")):
        raise HTTPException(status_code=400, detail="Document file not found")
    
    # Delete existing chunks
    vector_service.delete_document_chunks(doc_id)
    
    # Reprocess
    background_tasks.add_task(_process_document, doc_id, doc["file_path"], doc["file_name"])
    
    return {"message": "Reindexing started", "doc_id": doc_id}
