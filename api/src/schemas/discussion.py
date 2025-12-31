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
    status: str  # none, running, completed, failed, stale
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    windows_processed: int = 0
    total_windows: int = 0
    discussions_found: int = 0
    tokens_used: int = 0
    error_message: Optional[str] = None
    # Incremental analysis fields
    mode: Optional[str] = None  # "full" or "incremental"
    new_messages_count: Optional[int] = None
    context_messages_count: Optional[int] = None


class AnalyzeRequest(BaseModel):
    """Request to start a new analysis."""
    pass  # No parameters needed for now, could add options later


class AnalyzeResponse(BaseModel):
    """Response when starting a new analysis."""
    message: str
    run_id: int


# =============================================================================
# Topic Schemas
# =============================================================================

class TopicBrief(BaseModel):
    """Brief topic info for list views."""
    id: int
    name: str
    description: Optional[str] = None
    color: str
    discussion_count: int = 0
    
    class Config:
        from_attributes = True


class TopicListResponse(BaseModel):
    """Response for listing topics."""
    topics: List[TopicBrief]


class TopicClassificationStatusResponse(BaseModel):
    """Status of topic classification run."""
    status: str  # none, running, completed, failed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    topics_created: int = 0
    discussions_classified: int = 0
    error_message: Optional[str] = None


class ClassifyTopicsResponse(BaseModel):
    """Response when starting topic classification."""
    message: str
    run_id: int


# AI Response schema for topic classification
class TopicDefinition(BaseModel):
    """A topic definition from AI."""
    name: str
    description: str


class TopicAssignment(BaseModel):
    """Assignment of a discussion to topics."""
    discussion_id: int
    topic_names: List[str]


class TopicClassificationAIResponse(BaseModel):
    """Complete response from AI for topic classification."""
    topics: List[TopicDefinition]
    assignments: List[TopicAssignment]


# Updated DiscussionBrief to include topics
class DiscussionBriefWithTopics(DiscussionBrief):
    """Discussion brief with topic info."""
    topics: List[TopicBrief] = []
