from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uuid


# ===== Document Models =====

class DocumentMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    author: str = ""
    year: Optional[int] = None
    edition: Optional[str] = None
    legal_subject: str = ""  # matéria jurídica
    legal_institute: str = ""  # instituto jurídico
    file_path: str = ""
    file_name: str = ""
    file_hash: str = ""  # SHA256
    file_type: str = ""  # pdf or epub
    file_size: int = 0
    total_pages: Optional[int] = None
    total_chunks: int = 0
    status: str = "pending"  # pending, processing, indexed, error
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentUploadResponse(BaseModel):
    id: str
    file_name: str
    status: str
    message: str


class DocumentListResponse(BaseModel):
    documents: List[DocumentMetadata]
    total: int


class DocumentUpdateRequest(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    year: Optional[int] = None
    edition: Optional[str] = None
    legal_subject: Optional[str] = None
    legal_institute: Optional[str] = None


# ===== Chat Models =====

class ChatMessage(BaseModel):
    role: str  # user or assistant
    content: str


class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))
    max_sources: int = 10


class SourceReference(BaseModel):
    author: str
    title: str
    year: Optional[int] = None
    chunk_text: str
    relevance_score: float
    page: Optional[int] = None


class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceReference] = []
    session_id: str
    question: str
    processing_time: float = 0.0
    chunks_retrieved: int = 0


# ===== System Models =====

class SystemStats(BaseModel):
    total_documents: int = 0
    indexed_documents: int = 0
    total_chunks: int = 0
    vector_store_size: int = 0
    embedding_model: str = ""
    llm_model: str = ""
