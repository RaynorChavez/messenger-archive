from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel

from ..db import get_db, Message, Person, Room
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
            "notes": person.notes,
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
