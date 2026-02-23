"""JuristaAI - Advanced Legal Doctrinal AI Server"""

from fastapi import FastAPI, APIRouter
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
db_name = os.environ.get('DB_NAME', 'jurista_ai')
client = AsyncIOMotorClient(mongo_url)
db = client[db_name]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("=" * 60)
    logger.info("JuristaAI - Starting up...")
    logger.info(f"Database: {db_name}")
    logger.info(f"Embedding model: {os.environ.get('EMBEDDING_MODEL', 'default')}")
    logger.info(f"LLM model: {os.environ.get('LLM_MODEL', 'default')}")
    logger.info("=" * 60)
    
    # Pre-warm the embedding model in background
    # (it will load on first use, but we log readiness)
    try:
        from services import vector_service
        stats = vector_service.get_stats()
        logger.info(f"Vector store ready. Chunks: {stats.get('total_chunks', 0)}")
    except Exception as e:
        logger.warning(f"Vector store initialization deferred: {e}")
    
    # Create MongoDB indexes
    try:
        await db.documents.create_index("id", unique=True)
        await db.documents.create_index("file_hash")
        await db.documents.create_index("status")
        await db.documents.create_index("author")
        await db.documents.create_index("legal_subject")
        logger.info("MongoDB indexes created")
    except Exception as e:
        logger.warning(f"Error creating indexes: {e}")
    
    yield
    
    # Shutdown
    logger.info("JuristaAI shutting down...")
    client.close()


# Create FastAPI app
app = FastAPI(
    title="JuristaAI",
    description="Advanced Legal Doctrinal AI Assistant",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create API router with /api prefix
api_router = APIRouter(prefix="/api")


# Health check
@api_router.get("/")
async def root():
    return {
        "name": "JuristaAI",
        "version": "1.0.0",
        "description": "Advanced Legal Doctrinal AI Assistant"
    }


@api_router.get("/health")
async def health_check():
    try:
        from services import vector_service
        stats = vector_service.get_stats()
        doc_count = await db.documents.count_documents({})
        return {
            "status": "healthy",
            "database": "connected",
            "documents": doc_count,
            "vector_chunks": stats.get("total_chunks", 0)
        }
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


# Import and register route modules
from routes import document_routes, chat_routes

# Set database references
document_routes.set_db(db)
chat_routes.set_db(db)

# Include route modules
api_router.include_router(document_routes.router)
api_router.include_router(chat_routes.router)

# Include the API router
app.include_router(api_router)

logger.info("JuristaAI server configured successfully")
