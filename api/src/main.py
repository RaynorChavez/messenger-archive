import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import (
    auth_router,
    messages_router,
    people_router,
    threads_router,
    stats_router,
    settings_router,
    database_router,
    discussions_router,
    search_router,
    virtual_chat_router,
    rooms_router,
)
from .services.ai import init_ai_service
from .services.embeddings import init_embedding_service
from .services.virtual_chat import init_virtual_chat_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    # Startup
    settings = get_settings()
    if settings.gemini_api_key:
        init_ai_service(
            api_key=settings.gemini_api_key,
            max_tokens_per_minute=settings.gemini_rate_limit_tokens_per_min
        )
        init_embedding_service(api_key=settings.gemini_api_key)
        init_virtual_chat_service(api_key=settings.gemini_api_key)
        logger.info("AI, Embedding, and Virtual Chat services initialized")
    else:
        logger.warning("GEMINI_API_KEY not set - AI features disabled")
    
    yield
    
    # Shutdown
    logger.info("Shutting down")


app = FastAPI(
    title="Messenger Archive API",
    description="API for browsing archived Messenger conversations",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router, prefix="/api")
app.include_router(messages_router, prefix="/api")
app.include_router(people_router, prefix="/api")
app.include_router(threads_router, prefix="/api")
app.include_router(stats_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(database_router, prefix="/api")
app.include_router(discussions_router, prefix="/api")
app.include_router(search_router, prefix="/api")
app.include_router(virtual_chat_router, prefix="/api")
app.include_router(rooms_router, prefix="/api")


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
