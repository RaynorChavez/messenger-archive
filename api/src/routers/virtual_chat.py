"""
Virtual Chat Router - API endpoints for AI-powered group chat.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List

from ..db import get_db, VirtualConversation, VirtualParticipant, VirtualMessage
from ..auth import get_current_session
from ..schemas.virtual_chat import (
    CreateConversationRequest,
    ConversationResponse,
    ConversationWithMessagesResponse,
    VirtualMessageResponse,
    ParticipantBrief,
    SendMessageRequest,
)
from ..services.virtual_chat import get_virtual_chat_service

router = APIRouter(prefix="/virtual-chat", tags=["virtual-chat"])


# =============================================================================
# Helper Functions
# =============================================================================

def _build_participant_brief(participant: VirtualParticipant) -> ParticipantBrief:
    """Build a ParticipantBrief from a VirtualParticipant."""
    return ParticipantBrief(
        person_id=participant.person_id,
        display_name=participant.person.display_name if participant.person else None,
        avatar_url=participant.person.avatar_url if participant.person else None,
    )


def _build_message_response(message: VirtualMessage) -> VirtualMessageResponse:
    """Build a VirtualMessageResponse from a VirtualMessage."""
    return VirtualMessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_type=message.sender_type,
        person_id=message.person_id,
        person_display_name=message.person.display_name if message.person else None,
        person_avatar_url=message.person.avatar_url if message.person else None,
        content=message.content,
        created_at=message.created_at,
    )


def _build_conversation_response(conversation: VirtualConversation) -> ConversationResponse:
    """Build a ConversationResponse from a VirtualConversation."""
    return ConversationResponse(
        id=conversation.id,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        participants=[_build_participant_brief(p) for p in conversation.participants],
    )


def _build_conversation_with_messages_response(
    conversation: VirtualConversation
) -> ConversationWithMessagesResponse:
    """Build a ConversationWithMessagesResponse from a VirtualConversation."""
    return ConversationWithMessagesResponse(
        id=conversation.id,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        participants=[_build_participant_brief(p) for p in conversation.participants],
        messages=[_build_message_response(m) for m in conversation.messages],
    )


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    request: CreateConversationRequest,
    db: Session = Depends(get_db),
    session: dict = Depends(get_current_session),
):
    """Create a new virtual conversation with the specified participants."""
    if not request.participant_ids:
        raise HTTPException(status_code=400, detail="At least one participant is required")
    
    service = get_virtual_chat_service()
    
    try:
        conversation = service.create_conversation(db, request.participant_ids)
        return _build_conversation_response(conversation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/conversations/{conversation_id}", response_model=ConversationWithMessagesResponse)
async def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    session: dict = Depends(get_current_session),
):
    """Get a conversation with all its messages."""
    conversation = db.query(VirtualConversation).filter(
        VirtualConversation.id == conversation_id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return _build_conversation_with_messages_response(conversation)


@router.post("/conversations/{conversation_id}/participants")
async def add_participant(
    conversation_id: int,
    person_id: int,
    db: Session = Depends(get_db),
    session: dict = Depends(get_current_session),
):
    """Add a participant to an existing conversation."""
    service = get_virtual_chat_service()
    
    conversation = service.get_conversation(db, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    try:
        participant = service.add_participant(db, conversation_id, person_id)
        return _build_participant_brief(participant)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/conversations/{conversation_id}/message")
async def send_message(
    conversation_id: int,
    request: SendMessageRequest,
    db: Session = Depends(get_db),
    session: dict = Depends(get_current_session),
):
    """Send a message and stream agent responses via SSE.
    
    Returns a Server-Sent Events stream with the following event types:
    - user_message: User message was saved
    - thinking: An agent is generating a response
    - chunk: A text chunk from an agent
    - agent_done: An agent finished responding
    - complete: All agents have finished
    - error: An error occurred
    """
    service = get_virtual_chat_service()
    
    conversation = service.get_conversation(db, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="Message content is required")
    
    async def event_generator():
        async for event in service.process_message(db, conversation_id, request.content):
            yield event
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )
