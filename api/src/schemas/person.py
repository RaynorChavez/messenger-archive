from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class PersonResponse(BaseModel):
    """Person response with stats."""
    id: int
    matrix_user_id: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    fb_profile_url: Optional[str] = None
    notes: Optional[str] = None
    message_count: int = 0
    last_message_at: Optional[datetime] = None
    created_at: datetime
    
    # AI Summary fields
    ai_summary: Optional[str] = None
    ai_summary_generated_at: Optional[datetime] = None
    ai_summary_stale: bool = False  # True if 30+ new messages since last summary
    
    class Config:
        from_attributes = True


class PersonListResponse(BaseModel):
    """List of people."""
    people: List[PersonResponse]
    total: int


class PersonUpdate(BaseModel):
    """Update person notes."""
    notes: Optional[str] = None
