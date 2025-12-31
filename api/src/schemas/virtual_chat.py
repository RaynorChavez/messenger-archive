from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List, Literal


# =============================================================================
# Participant Schema
# =============================================================================

class ParticipantBrief(BaseModel):
    """Brief participant info for responses."""
    person_id: int
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    
    class Config:
        from_attributes = True


# =============================================================================
# Message Schemas
# =============================================================================

class VirtualMessageResponse(BaseModel):
    """A message in a virtual conversation."""
    id: int
    conversation_id: int
    sender_type: Literal["user", "agent"]
    person_id: Optional[int] = None  # NULL for user messages
    person_display_name: Optional[str] = None  # Populated for agent messages
    person_avatar_url: Optional[str] = None
    content: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class SendMessageRequest(BaseModel):
    """Request to send a message in a virtual conversation."""
    content: str


# =============================================================================
# Conversation Schemas
# =============================================================================

class CreateConversationRequest(BaseModel):
    """Request to create a new virtual conversation."""
    participant_ids: List[int]  # List of person IDs to include as AI agents


class ConversationResponse(BaseModel):
    """Virtual conversation response."""
    id: int
    created_at: datetime
    updated_at: datetime
    participants: List[ParticipantBrief]
    
    class Config:
        from_attributes = True


class ConversationWithMessagesResponse(BaseModel):
    """Virtual conversation with all messages."""
    id: int
    created_at: datetime
    updated_at: datetime
    participants: List[ParticipantBrief]
    messages: List[VirtualMessageResponse]
    
    class Config:
        from_attributes = True


# =============================================================================
# SSE Event Schemas
# =============================================================================

class SSEUserMessageEvent(BaseModel):
    """SSE event: user message saved."""
    type: Literal["user_message"] = "user_message"
    id: int
    content: str


class SSEThinkingEvent(BaseModel):
    """SSE event: agent is thinking."""
    type: Literal["thinking"] = "thinking"
    person_id: int
    display_name: str


class SSEChunkEvent(BaseModel):
    """SSE event: agent text chunk."""
    type: Literal["chunk"] = "chunk"
    person_id: int
    text: str


class SSEAgentDoneEvent(BaseModel):
    """SSE event: agent finished responding."""
    type: Literal["agent_done"] = "agent_done"
    person_id: int
    message_id: Optional[int] = None  # NULL if no response


class SSECompleteEvent(BaseModel):
    """SSE event: all agents complete."""
    type: Literal["complete"] = "complete"


class SSEErrorEvent(BaseModel):
    """SSE event: error occurred."""
    type: Literal["error"] = "error"
    message: str
