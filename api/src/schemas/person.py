from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class PersonResponse(BaseModel):
    """Person response with stats."""
    id: int
    matrix_user_id: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    notes: Optional[str] = None
    message_count: int = 0
    last_message_at: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class PersonListResponse(BaseModel):
    """List of people."""
    people: List[PersonResponse]
    total: int


class PersonUpdate(BaseModel):
    """Update person notes."""
    notes: Optional[str] = None
