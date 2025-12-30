from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class PersonBrief(BaseModel):
    """Brief person info for embedding in messages."""
    id: int
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    
    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    """Single message response."""
    id: int
    content: Optional[str] = None
    timestamp: datetime
    sender: Optional[PersonBrief] = None
    reply_to_message_id: Optional[int] = None
    reply_to_sender: Optional[PersonBrief] = None
    
    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    """Paginated list of messages."""
    messages: List[MessageResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
