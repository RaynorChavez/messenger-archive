from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import httpx

from ..db import get_db, Message
from ..auth import get_current_session

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
