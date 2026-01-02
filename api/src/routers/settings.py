from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import httpx

from ..db import get_db, Message, ImageDescription
from ..auth import get_current_session
from ..services.image_description import get_image_description_service

router = APIRouter(prefix="/settings", tags=["settings"])

SYNAPSE_URL = "http://synapse:8008"


class BridgeStatus(BaseModel):
    """Bridge connection status."""
    messenger_connected: bool
    last_synced: Optional[datetime] = None
    matrix_running: bool


class ArchiveStats(BaseModel):
    """Archive statistics."""
    messages_archived: int
    database_size_mb: float
    oldest_message: Optional[datetime] = None


class SettingsResponse(BaseModel):
    """Settings page data."""
    bridge: BridgeStatus
    archive: ArchiveStats


async def check_synapse_health() -> bool:
    """Check if Synapse is responding."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{SYNAPSE_URL}/_matrix/client/versions")
            return response.status_code == 200
    except Exception:
        return False


@router.get("/status", response_model=SettingsResponse)
async def get_settings_status(
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get bridge status and archive stats."""
    # Message count
    message_count = db.query(func.count(Message.id)).scalar() or 0
    
    # Oldest message
    oldest = db.query(func.min(Message.timestamp)).scalar()
    
    # Latest message (for last synced)
    latest = db.query(func.max(Message.timestamp)).scalar()
    
    # Database size from PostgreSQL
    try:
        result = db.execute(text("SELECT pg_database_size('messenger_archive')")).scalar()
        db_size_mb = round(result / (1024 * 1024), 2) if result else 0
    except Exception:
        db_size_mb = round(message_count * 0.001, 2)  # Fallback estimate
    
    # Check Synapse health
    matrix_running = await check_synapse_health()
    
    # Messenger is "connected" if we have recent messages (within last hour)
    # or if there are any messages at all
    messenger_connected = message_count > 0 or matrix_running
    
    return SettingsResponse(
        bridge=BridgeStatus(
            messenger_connected=messenger_connected,
            last_synced=latest,
            matrix_running=matrix_running
        ),
        archive=ArchiveStats(
            messages_archived=message_count,
            database_size_mb=db_size_mb,
            oldest_message=oldest
        )
    )


class ImageProcessingResponse(BaseModel):
    """Response for image processing endpoint."""
    processed: int
    pending: int
    errors: int


@router.post("/images/process", response_model=ImageProcessingResponse)
async def process_pending_images(
    limit: int = 10,
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Process pending images through Gemini Vision to generate descriptions."""
    service = get_image_description_service()
    if not service:
        raise HTTPException(status_code=503, detail="Image description service not initialized")
    
    # Process images in thread pool to avoid blocking
    processed = await run_in_threadpool(service.process_pending_images, db, limit)
    
    # Get counts for response
    pending = db.query(func.count(ImageDescription.id)).filter(
        ImageDescription.processed_at.is_(None),
        ImageDescription.error.is_(None)
    ).scalar() or 0
    
    errors = db.query(func.count(ImageDescription.id)).filter(
        ImageDescription.error.isnot(None)
    ).scalar() or 0
    
    return ImageProcessingResponse(
        processed=processed,
        pending=pending,
        errors=errors
    )


@router.get("/images/status", response_model=ImageProcessingResponse)
async def get_image_processing_status(
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get current image processing status."""
    total = db.query(func.count(ImageDescription.id)).scalar() or 0
    
    pending = db.query(func.count(ImageDescription.id)).filter(
        ImageDescription.processed_at.is_(None),
        ImageDescription.error.is_(None)
    ).scalar() or 0
    
    errors = db.query(func.count(ImageDescription.id)).filter(
        ImageDescription.error.isnot(None)
    ).scalar() or 0
    
    processed = total - pending - errors
    
    return ImageProcessingResponse(
        processed=processed,
        pending=pending,
        errors=errors
    )
