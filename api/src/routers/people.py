from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc, extract
from typing import Optional, Literal
from datetime import datetime, timedelta
import logging

from ..db import get_db, Person, Message
from ..auth import get_current_session
from ..schemas.person import PersonResponse, PersonListResponse, PersonUpdate
from ..schemas.message import MessageResponse, MessageListResponse, PersonBrief
from ..services.ai import get_ai_service, RateLimitExceeded

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/people", tags=["people"])

STALE_THRESHOLD = 30  # Messages since last summary before considered stale


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
    
    results = query.order_by(desc(func.coalesce(message_count_subq.c.message_count, 0))).all()
    
    people = []
    for person, message_count, last_message_at in results:
        people.append(PersonResponse(
            id=person.id,
            matrix_user_id=person.matrix_user_id,
            display_name=person.display_name,
            avatar_url=person.avatar_url,
            fb_profile_url=person.fb_profile_url,
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
    
    message_count = stats.count or 0
    
    # Calculate if summary is stale (30+ new messages since last generation)
    ai_summary_stale = False
    if person.ai_summary:
        messages_since_summary = message_count - (person.ai_summary_message_count or 0)
        ai_summary_stale = messages_since_summary >= STALE_THRESHOLD
    
    return PersonResponse(
        id=person.id,
        matrix_user_id=person.matrix_user_id,
        display_name=person.display_name,
        avatar_url=person.avatar_url,
        fb_profile_url=person.fb_profile_url,
        notes=person.notes,
        message_count=message_count,
        last_message_at=stats.last_at,
        created_at=person.created_at,
        ai_summary=person.ai_summary,
        ai_summary_generated_at=person.ai_summary_generated_at,
        ai_summary_stale=ai_summary_stale
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
        fb_profile_url=person.fb_profile_url,
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


@router.post("/{person_id}/generate-summary", response_model=PersonResponse)
async def generate_person_summary(
    person_id: int,
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Generate AI summary for a person based on their messages."""
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    # Fetch ALL messages from this person, ordered by timestamp
    messages = (
        db.query(Message.timestamp, Message.content)
        .filter(Message.sender_id == person_id)
        .filter(Message.content.isnot(None))
        .filter(Message.content != "")
        .order_by(asc(Message.timestamp))
        .all()
    )
    
    if not messages:
        raise HTTPException(status_code=400, detail="No messages found for this person")
    
    # Format messages as list of (timestamp, content) tuples
    message_tuples = [(msg.timestamp, msg.content) for msg in messages]
    
    try:
        ai_service = get_ai_service()
        summary = await ai_service.generate_profile_summary(
            person_name=person.display_name or "Unknown",
            messages=message_tuples
        )
        
        # Update person record
        person.ai_summary = summary
        person.ai_summary_generated_at = datetime.utcnow()
        person.ai_summary_message_count = len(messages)
        db.commit()
        db.refresh(person)
        
        logger.info(f"Generated AI summary for person {person_id} ({person.display_name})")
        
    except RateLimitExceeded as e:
        return JSONResponse(
            status_code=429,
            content={
                "detail": f"Rate limit exceeded. Try again in {e.retry_after:.0f} seconds.",
                "retry_after": e.retry_after
            }
        )
    except Exception as e:
        logger.error(f"Error generating summary for person {person_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate summary: {str(e)}")
    
    # Get message stats for response
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
        fb_profile_url=person.fb_profile_url,
        notes=person.notes,
        message_count=stats.count or 0,
        last_message_at=stats.last_at,
        created_at=person.created_at,
        ai_summary=person.ai_summary,
        ai_summary_generated_at=person.ai_summary_generated_at,
        ai_summary_stale=False  # Just generated, not stale
    )


@router.get("/{person_id}/activity")
async def get_person_activity(
    person_id: int,
    period: Literal["all", "year", "6months", "3months", "month"] = "6months",
    granularity: Literal["day", "week", "month"] = "week",
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get activity stats for a person over time."""
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    # Calculate date range
    now = datetime.utcnow()
    if period == "month":
        start_date = now - timedelta(days=30)
    elif period == "3months":
        start_date = now - timedelta(days=90)
    elif period == "6months":
        start_date = now - timedelta(days=180)
    elif period == "year":
        start_date = now - timedelta(days=365)
    else:  # all
        start_date = None
    
    # Build query based on granularity
    if granularity == "day":
        date_trunc = func.date(Message.timestamp)
    elif granularity == "week":
        date_trunc = func.date_trunc('week', Message.timestamp)
    else:  # month
        date_trunc = func.date_trunc('month', Message.timestamp)
    
    query = (
        db.query(
            date_trunc.label("period"),
            func.count(Message.id).label("count")
        )
        .filter(Message.sender_id == person_id)
    )
    
    if start_date:
        query = query.filter(Message.timestamp >= start_date)
    
    activity_data = (
        query
        .group_by(date_trunc)
        .order_by(date_trunc)
        .all()
    )
    
    # Get total message count
    total_messages = db.query(func.count(Message.id)).filter(
        Message.sender_id == person_id
    ).scalar() or 0
    
    # Get most active day of week (0=Sunday, 6=Saturday)
    day_of_week_query = (
        db.query(
            extract('dow', Message.timestamp).label("dow"),
            func.count(Message.id).label("count")
        )
        .filter(Message.sender_id == person_id)
        .group_by(extract('dow', Message.timestamp))
        .order_by(desc(func.count(Message.id)))
        .first()
    )
    
    day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    most_active_day = day_names[int(day_of_week_query.dow)] if day_of_week_query else None
    
    # Get most active hour
    hour_query = (
        db.query(
            extract('hour', Message.timestamp).label("hour"),
            func.count(Message.id).label("count")
        )
        .filter(Message.sender_id == person_id)
        .group_by(extract('hour', Message.timestamp))
        .order_by(desc(func.count(Message.id)))
        .first()
    )
    
    most_active_hour = int(hour_query.hour) if hour_query else None
    
    return {
        "person_id": person_id,
        "period": period,
        "granularity": granularity,
        "data": [
            {"date": row.period.isoformat() if hasattr(row.period, 'isoformat') else str(row.period), "count": row.count}
            for row in activity_data
        ],
        "total_messages": total_messages,
        "most_active_day": most_active_day,
        "most_active_hour": most_active_hour
    }
