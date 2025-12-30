from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional

from ..db import get_db, Person, Message
from ..auth import get_current_session
from ..schemas.person import PersonResponse, PersonListResponse, PersonUpdate
from ..schemas.message import MessageResponse, MessageListResponse, PersonBrief

router = APIRouter(prefix="/people", tags=["people"])


@router.get("", response_model=PersonListResponse)
async def list_people(
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """List all people with message counts."""
    # Subquery for message counts
    message_count_subq = (
        db.query(
            Message.sender_id,
            func.count(Message.id).label("message_count"),
            func.max(Message.timestamp).label("last_message_at")
        )
        .group_by(Message.sender_id)
        .subquery()
    )
    
    query = (
        db.query(Person, message_count_subq.c.message_count, message_count_subq.c.last_message_at)
        .outerjoin(message_count_subq, Person.id == message_count_subq.c.sender_id)
    )
    
    if search:
        query = query.filter(Person.display_name.ilike(f"%{search}%"))
    
    results = query.order_by(desc(message_count_subq.c.message_count.nullsfirst())).all()
    
    people = []
    for person, message_count, last_message_at in results:
        people.append(PersonResponse(
            id=person.id,
            matrix_user_id=person.matrix_user_id,
            display_name=person.display_name,
            avatar_url=person.avatar_url,
            notes=person.notes,
            message_count=message_count or 0,
            last_message_at=last_message_at,
            created_at=person.created_at
        ))
    
    return PersonListResponse(people=people, total=len(people))


@router.get("/{person_id}", response_model=PersonResponse)
async def get_person(
    person_id: int,
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get a single person by ID."""
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    # Get message stats
    stats = (
        db.query(
            func.count(Message.id).label("count"),
            func.max(Message.timestamp).label("last_at")
        )
        .filter(Message.sender_id == person_id)
        .first()
    )
    
    return PersonResponse(
        id=person.id,
        matrix_user_id=person.matrix_user_id,
        display_name=person.display_name,
        avatar_url=person.avatar_url,
        notes=person.notes,
        message_count=stats.count or 0,
        last_message_at=stats.last_at,
        created_at=person.created_at
    )


@router.patch("/{person_id}", response_model=PersonResponse)
async def update_person(
    person_id: int,
    update: PersonUpdate,
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Update a person's notes."""
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    if update.notes is not None:
        person.notes = update.notes
    
    db.commit()
    db.refresh(person)
    
    # Get message stats
    stats = (
        db.query(
            func.count(Message.id).label("count"),
            func.max(Message.timestamp).label("last_at")
        )
        .filter(Message.sender_id == person_id)
        .first()
    )
    
    return PersonResponse(
        id=person.id,
        matrix_user_id=person.matrix_user_id,
        display_name=person.display_name,
        avatar_url=person.avatar_url,
        notes=person.notes,
        message_count=stats.count or 0,
        last_message_at=stats.last_at,
        created_at=person.created_at
    )


@router.get("/{person_id}/messages", response_model=MessageListResponse)
async def get_person_messages(
    person_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get messages from a specific person."""
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    query = db.query(Message).filter(Message.sender_id == person_id)
    total = query.count()
    
    offset = (page - 1) * page_size
    messages = query.order_by(desc(Message.timestamp)).offset(offset).limit(page_size).all()
    
    sender_brief = PersonBrief(
        id=person.id,
        display_name=person.display_name,
        avatar_url=person.avatar_url
    )
    
    message_responses = [
        MessageResponse(
            id=msg.id,
            content=msg.content,
            timestamp=msg.timestamp,
            sender=sender_brief,
            reply_to_message_id=msg.reply_to_message_id,
            reply_to_sender=None
        )
        for msg in messages
    ]
    
    total_pages = (total + page_size - 1) // page_size
    
    return MessageListResponse(
        messages=message_responses,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )
