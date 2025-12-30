from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional
from datetime import datetime

from ..db import get_db, Message, Person
from ..auth import get_current_session
from ..schemas.message import MessageResponse, MessageListResponse, PersonBrief

router = APIRouter(prefix="/messages", tags=["messages"])


@router.get("", response_model=MessageListResponse)
async def list_messages(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    sender_id: Optional[int] = None,
    search: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """List messages with pagination and filters."""
    query = db.query(Message).join(Person, Message.sender_id == Person.id, isouter=True)
    
    # Apply filters
    if sender_id:
        query = query.filter(Message.sender_id == sender_id)
    if search:
        query = query.filter(Message.content.ilike(f"%{search}%"))
    if start_date:
        query = query.filter(Message.timestamp >= start_date)
    if end_date:
        query = query.filter(Message.timestamp <= end_date)
    
    # Get total count
    total = query.count()
    
    # Paginate
    offset = (page - 1) * page_size
    messages = query.order_by(desc(Message.timestamp)).offset(offset).limit(page_size).all()
    
    # Build response
    message_responses = []
    for msg in messages:
        sender_brief = None
        if msg.sender:
            sender_brief = PersonBrief(
                id=msg.sender.id,
                display_name=msg.sender.display_name,
                avatar_url=msg.sender.avatar_url
            )
        
        reply_to_sender = None
        if msg.reply_to and msg.reply_to.sender:
            reply_to_sender = PersonBrief(
                id=msg.reply_to.sender.id,
                display_name=msg.reply_to.sender.display_name,
                avatar_url=msg.reply_to.sender.avatar_url
            )
        
        message_responses.append(MessageResponse(
            id=msg.id,
            content=msg.content,
            timestamp=msg.timestamp,
            sender=sender_brief,
            reply_to_message_id=msg.reply_to_message_id,
            reply_to_sender=reply_to_sender
        ))
    
    total_pages = (total + page_size - 1) // page_size
    
    return MessageListResponse(
        messages=message_responses,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/search")
async def search_messages(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Full-text search across messages."""
    # Use PostgreSQL full-text search
    query = db.query(Message).filter(
        func.to_tsvector('english', Message.content).match(q)
    )
    
    total = query.count()
    offset = (page - 1) * page_size
    messages = query.order_by(desc(Message.timestamp)).offset(offset).limit(page_size).all()
    
    message_responses = []
    for msg in messages:
        sender_brief = None
        if msg.sender:
            sender_brief = PersonBrief(
                id=msg.sender.id,
                display_name=msg.sender.display_name,
                avatar_url=msg.sender.avatar_url
            )
        
        message_responses.append(MessageResponse(
            id=msg.id,
            content=msg.content,
            timestamp=msg.timestamp,
            sender=sender_brief,
            reply_to_message_id=msg.reply_to_message_id,
            reply_to_sender=None
        ))
    
    total_pages = (total + page_size - 1) // page_size
    
    return MessageListResponse(
        messages=message_responses,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{message_id}", response_model=MessageResponse)
async def get_message(
    message_id: int,
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get a single message by ID."""
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Message not found")
    
    sender_brief = None
    if msg.sender:
        sender_brief = PersonBrief(
            id=msg.sender.id,
            display_name=msg.sender.display_name,
            avatar_url=msg.sender.avatar_url
        )
    
    return MessageResponse(
        id=msg.id,
        content=msg.content,
        timestamp=msg.timestamp,
        sender=sender_brief,
        reply_to_message_id=msg.reply_to_message_id,
        reply_to_sender=None
    )
