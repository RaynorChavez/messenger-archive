"""Pydantic schemas for discussion analysis and API responses."""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Literal, Union


# =============================================================================
# AI Response Schemas (for parsing Gemini JSON output)
# =============================================================================

class DiscussionAssignment(BaseModel):
    """Assignment of a message to a discussion."""
    discussion_id: Union[int, str]  # int for existing, or "NEW", "NEW_1", etc.
    title: Optional[str] = None  # Required if discussion_id starts with "NEW"
    confidence: float = Field(ge=0.0, le=1.0)


class MessageClassification(BaseModel):
    """Classification result for a single message."""
    message_id: int
    assignments: List[DiscussionAssignment]


class NewDiscussionInfo(BaseModel):
    """Info about a new discussion created in a window."""
    temp_id: str
    title: str


class WindowClassificationResponse(BaseModel):
    """Complete response from AI for a window classification."""
    classifications: List[MessageClassification]
    discussions_ended: List[int] = []
    new_discussions: List[NewDiscussionInfo] = []


# =============================================================================
# API Response Schemas
# =============================================================================

class PersonBrief(BaseModel):
    """Brief person info for display."""
    id: int
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None


class DiscussionMessageResponse(BaseModel):
    """A message within a discussion with confidence score."""
    id: int
    content: Optional[str] = None
    timestamp: datetime
    sender: Optional[PersonBrief] = None
    confidence: float
    
    class Config:
        from_attributes = True


class DiscussionBrief(BaseModel):
    """Brief discussion info for list views."""
    id: int
    title: str
    summary: Optional[str] = None
    started_at: datetime
    ended_at: datetime
    message_count: int
    participant_count: int
    
    class Config:
        from_attributes = True


class DiscussionFull(BaseModel):
    """Full discussion with messages."""
    id: int
    title: str
    summary: Optional[str] = None
    started_at: datetime
    ended_at: datetime
    message_count: int
    participant_count: int
    messages: List[DiscussionMessageResponse]
    
    class Config:
        from_attributes = True


class DiscussionListResponse(BaseModel):
    """Response for listing discussions."""
    discussions: List[DiscussionBrief]
    total: int
    page: int
    page_size: int
    total_pages: int


class AnalysisStatusResponse(BaseModel):
    """Status of discussion analysis run."""
    status: str  # none, running, completed, failed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    windows_processed: int = 0
    total_windows: int = 0
    discussions_found: int = 0
    tokens_used: int = 0
    error_message: Optional[str] = None


class AnalyzeRequest(BaseModel):
    """Request to start a new analysis."""
    pass  # No parameters needed for now, could add options later


class AnalyzeResponse(BaseModel):
    """Response when starting a new analysis."""
    message: str
    run_id: int
