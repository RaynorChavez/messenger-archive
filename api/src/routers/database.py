from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel

from ..db import get_db, Message, Person, Room, Discussion, DiscussionMessage, Topic, DiscussionTopic
from ..auth import get_current_session

router = APIRouter(prefix="/database", tags=["database"])


class TableRow(BaseModel):
    """Generic table row."""
    class Config:
        from_attributes = True


class MessagesTableResponse(BaseModel):
    """Messages table response."""
    rows: List[dict]
    total: int
    page: int
    page_size: int
    total_pages: int


class PeopleTableResponse(BaseModel):
    """People table response."""
    rows: List[dict]
    total: int
    page: int
    page_size: int
    total_pages: int


class RoomsTableResponse(BaseModel):
    """Rooms table response."""
    rows: List[dict]
    total: int
    page: int
    page_size: int
    total_pages: int


@router.get("/messages", response_model=MessagesTableResponse)
async def get_messages_table(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get raw messages table data."""
    total = db.query(func.count(Message.id)).scalar() or 0
    offset = (page - 1) * page_size
    
    messages = db.query(Message).order_by(Message.id.desc()).offset(offset).limit(page_size).all()
    
    rows = []
    for msg in messages:
        rows.append({
            "id": msg.id,
            "matrix_event_id": msg.matrix_event_id,
            "room_id": msg.room_id,
            "sender_id": msg.sender_id,
            "content": msg.content[:100] + "..." if msg.content and len(msg.content) > 100 else msg.content,
            "reply_to_message_id": msg.reply_to_message_id,
            "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        })
    
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    return MessagesTableResponse(
        rows=rows,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/people", response_model=PeopleTableResponse)
async def get_people_table(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get raw people table data."""
    total = db.query(func.count(Person.id)).scalar() or 0
    offset = (page - 1) * page_size
    
    people = db.query(Person).order_by(Person.id.desc()).offset(offset).limit(page_size).all()
    
    rows = []
    for person in people:
        rows.append({
            "id": person.id,
            "matrix_user_id": person.matrix_user_id,
            "display_name": person.display_name,
            "avatar_url": person.avatar_url,
            "fb_profile_url": person.fb_profile_url,
            "fb_name": person.fb_name,
            "notes": person.notes,
            "ai_summary": person.ai_summary[:100] + "..." if person.ai_summary and len(person.ai_summary) > 100 else person.ai_summary,
            "ai_summary_generated_at": person.ai_summary_generated_at.isoformat() if person.ai_summary_generated_at else None,
            "ai_summary_message_count": person.ai_summary_message_count,
            "created_at": person.created_at.isoformat() if person.created_at else None,
            "updated_at": person.updated_at.isoformat() if person.updated_at else None,
        })
    
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    return PeopleTableResponse(
        rows=rows,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/rooms", response_model=RoomsTableResponse)
async def get_rooms_table(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get raw rooms table data."""
    total = db.query(func.count(Room.id)).scalar() or 0
    offset = (page - 1) * page_size
    
    rooms = db.query(Room).order_by(Room.id.desc()).offset(offset).limit(page_size).all()
    
    rows = []
    for room in rooms:
        rows.append({
            "id": room.id,
            "matrix_room_id": room.matrix_room_id,
            "name": room.name,
            "is_group": room.is_group,
            "created_at": room.created_at.isoformat() if room.created_at else None,
        })
    
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    return RoomsTableResponse(
        rows=rows,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/discussions")
async def get_discussions_table(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get raw discussions table data."""
    total = db.query(func.count(Discussion.id)).scalar() or 0
    offset = (page - 1) * page_size
    
    discussions = db.query(Discussion).order_by(Discussion.id.desc()).offset(offset).limit(page_size).all()
    
    rows = []
    for d in discussions:
        rows.append({
            "id": d.id,
            "analysis_run_id": d.analysis_run_id,
            "title": d.title,
            "summary": d.summary[:100] + "..." if d.summary and len(d.summary) > 100 else d.summary,
            "started_at": d.started_at.isoformat() if d.started_at else None,
            "ended_at": d.ended_at.isoformat() if d.ended_at else None,
            "message_count": d.message_count,
            "participant_count": d.participant_count,
        })
    
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    return {
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }


@router.get("/discussion_messages")
async def get_discussion_messages_table(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get raw discussion_messages table data."""
    total = db.query(func.count(DiscussionMessage.discussion_id)).scalar() or 0
    offset = (page - 1) * page_size
    
    items = db.query(DiscussionMessage).order_by(DiscussionMessage.discussion_id.desc(), DiscussionMessage.message_id.desc()).offset(offset).limit(page_size).all()
    
    rows = []
    for item in items:
        rows.append({
            "discussion_id": item.discussion_id,
            "message_id": item.message_id,
            "confidence": item.confidence,
        })
    
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    return {
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }


@router.get("/topics")
async def get_topics_table(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get raw topics table data."""
    total = db.query(func.count(Topic.id)).scalar() or 0
    offset = (page - 1) * page_size
    
    topics = db.query(Topic).order_by(Topic.id.desc()).offset(offset).limit(page_size).all()
    
    rows = []
    for t in topics:
        rows.append({
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "color": t.color,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })
    
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    return {
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }


@router.get("/discussion_topics")
async def get_discussion_topics_table(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get raw discussion_topics table data."""
    total = db.query(func.count(DiscussionTopic.discussion_id)).scalar() or 0
    offset = (page - 1) * page_size
    
    items = db.query(DiscussionTopic).order_by(DiscussionTopic.discussion_id.desc(), DiscussionTopic.topic_id.desc()).offset(offset).limit(page_size).all()
    
    rows = []
    for item in items:
        rows.append({
            "discussion_id": item.discussion_id,
            "topic_id": item.topic_id,
        })
    
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    return {
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }
