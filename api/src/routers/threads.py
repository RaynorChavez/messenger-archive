from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from ..db import get_db, Message, Person
from ..auth import get_current_session
from ..schemas.message import PersonBrief

router = APIRouter(prefix="/threads", tags=["threads"])


class ThreadMessage(BaseModel):
    """Message within a thread."""
    id: int
    content: Optional[str] = None
    timestamp: datetime
    sender: Optional[PersonBrief] = None
    reply_to_message_id: Optional[int] = None
    depth: int = 0  # Nesting level in thread


class ThreadResponse(BaseModel):
    """A thread (conversation started by a message with replies)."""
    id: int
    root_message_id: int
    started_by: Optional[PersonBrief] = None
    started_at: datetime
    message_count: int
    last_message_at: datetime
    preview: Optional[str] = None
    messages: Optional[List[ThreadMessage]] = None


class ThreadListResponse(BaseModel):
    """List of threads."""
    threads: List[ThreadResponse]
    total: int
    page: int
    page_size: int


@router.get("", response_model=ThreadListResponse)
async def list_threads(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """
    List threads (conversations with replies).
    A thread is defined as a root message that has at least one reply.
    """
    # Find messages that are replied to (these are thread roots)
    thread_roots_subq = (
        db.query(Message.reply_to_message_id)
        .filter(Message.reply_to_message_id.isnot(None))
        .distinct()
        .subquery()
    )
    
    # Get root messages with reply counts
    root_messages = (
        db.query(
            Message,
            func.count(Message.id).label("reply_count"),
            func.max(Message.timestamp).label("last_reply_at")
        )
        .filter(Message.id.in_(
            db.query(thread_roots_subq.c.reply_to_message_id)
        ))
        .outerjoin(
            Message,
            Message.reply_to_message_id == Message.id
        )
        .group_by(Message.id)
        .order_by(desc(func.max(Message.timestamp)))
    )
    
    total = root_messages.count()
    offset = (page - 1) * page_size
    
    # Simplified query - just get messages that have replies
    reply_to_ids = (
        db.query(Message.reply_to_message_id)
        .filter(Message.reply_to_message_id.isnot(None))
        .distinct()
        .all()
    )
    reply_to_ids = [r[0] for r in reply_to_ids]
    
    if not reply_to_ids:
        return ThreadListResponse(threads=[], total=0, page=page, page_size=page_size)
    
    # Get the root messages
    root_msgs = (
        db.query(Message)
        .filter(Message.id.in_(reply_to_ids))
        .order_by(desc(Message.timestamp))
        .offset(offset)
        .limit(page_size)
        .all()
    )
    
    threads = []
    for root in root_msgs:
        # Count replies
        reply_count = (
            db.query(func.count(Message.id))
            .filter(Message.reply_to_message_id == root.id)
            .scalar()
        )
        
        # Get last reply timestamp
        last_reply = (
            db.query(func.max(Message.timestamp))
            .filter(Message.reply_to_message_id == root.id)
            .scalar()
        )
        
        sender_brief = None
        if root.sender:
            sender_brief = PersonBrief(
                id=root.sender.id,
                display_name=root.sender.display_name,
                avatar_url=root.sender.avatar_url
            )
        
        threads.append(ThreadResponse(
            id=root.id,
            root_message_id=root.id,
            started_by=sender_brief,
            started_at=root.timestamp,
            message_count=reply_count + 1,  # Include root message
            last_message_at=last_reply or root.timestamp,
            preview=root.content[:100] if root.content else None,
            messages=None
        ))
    
    return ThreadListResponse(
        threads=threads,
        total=len(reply_to_ids),
        page=page,
        page_size=page_size
    )


@router.get("/{thread_id}", response_model=ThreadResponse)
async def get_thread(
    thread_id: int,
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get a thread with all its messages."""
    from fastapi import HTTPException
    
    # Get the root message
    root = db.query(Message).filter(Message.id == thread_id).first()
    if not root:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    # Get all messages in this thread (recursive would be ideal, but for simplicity
    # we'll get direct replies for now)
    def get_thread_messages(root_id: int, depth: int = 0) -> List[ThreadMessage]:
        messages = []
        
        # Get the root message itself
        msg = db.query(Message).filter(Message.id == root_id).first()
        if msg:
            sender_brief = None
            if msg.sender:
                sender_brief = PersonBrief(
                    id=msg.sender.id,
                    display_name=msg.sender.display_name,
                    avatar_url=msg.sender.avatar_url
                )
            
            messages.append(ThreadMessage(
                id=msg.id,
                content=msg.content,
                timestamp=msg.timestamp,
                sender=sender_brief,
                reply_to_message_id=msg.reply_to_message_id,
                depth=depth
            ))
            
            # Get direct replies
            replies = (
                db.query(Message)
                .filter(Message.reply_to_message_id == root_id)
                .order_by(Message.timestamp)
                .all()
            )
            
            for reply in replies:
                messages.extend(get_thread_messages(reply.id, depth + 1))
        
        return messages
    
    thread_messages = get_thread_messages(thread_id)
    
    sender_brief = None
    if root.sender:
        sender_brief = PersonBrief(
            id=root.sender.id,
            display_name=root.sender.display_name,
            avatar_url=root.sender.avatar_url
        )
    
    last_msg = max(thread_messages, key=lambda m: m.timestamp) if thread_messages else None
    
    return ThreadResponse(
        id=root.id,
        root_message_id=root.id,
        started_by=sender_brief,
        started_at=root.timestamp,
        message_count=len(thread_messages),
        last_message_at=last_msg.timestamp if last_msg else root.timestamp,
        preview=root.content[:100] if root.content else None,
        messages=thread_messages
    )
