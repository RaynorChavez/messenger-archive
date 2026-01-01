from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc, extract
from typing import Optional, Literal, Dict, Any
from datetime import datetime, timedelta
import logging
import threading

from ..db import get_db, Person, Message, Room, RoomMember, SessionLocal
from ..auth import get_current_session
from ..schemas.person import PersonResponse, PersonListResponse, PersonUpdate
from ..schemas.message import MessageResponse, MessageListResponse, PersonBrief
from ..services.ai import get_ai_service, RateLimitExceeded
from ..services.virtual_chat import get_persona_cache
from ..config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/people", tags=["people"])

STALE_THRESHOLD = 30  # Messages since last summary before considered stale

# Track summary generation status per person
_summary_status: Dict[int, Dict[str, Any]] = {}


@router.get("", response_model=PersonListResponse)
async def list_people(
    search: Optional[str] = None,
    room_id: Optional[int] = Query(None, description="Filter by room membership"),
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """List all people with message counts. Optionally filter by room membership."""
    
    if room_id is not None:
        # When filtering by room, use room_members table for accurate per-room stats
        query = (
            db.query(
                Person,
                RoomMember.message_count,
                RoomMember.last_seen_at
            )
            .join(RoomMember, Person.id == RoomMember.person_id)
            .filter(RoomMember.room_id == room_id)
        )
        
        if search:
            query = query.filter(Person.display_name.ilike(f"%{search}%"))
        
        results = query.order_by(desc(RoomMember.message_count)).all()
        
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
    else:
        # No room filter - show all people with global message counts
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
    
    # Invalidate persona cache so virtual chat picks up new notes
    get_persona_cache().invalidate(person_id)
    
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


@router.get("/{person_id}/rooms")
async def get_person_rooms(
    person_id: int,
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get all rooms a person is in, with per-room stats."""
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    # Get room memberships with room details
    memberships = (
        db.query(RoomMember, Room)
        .join(Room, RoomMember.room_id == Room.id)
        .filter(RoomMember.person_id == person_id)
        .order_by(desc(RoomMember.message_count))
        .all()
    )
    
    rooms = []
    for membership, room in memberships:
        rooms.append({
            "room_id": room.id,
            "room_name": room.name,
            "avatar_url": room.avatar_url,
            "message_count": membership.message_count or 0,
            "first_seen_at": membership.first_seen_at.isoformat() if membership.first_seen_at else None,
            "last_seen_at": membership.last_seen_at.isoformat() if membership.last_seen_at else None,
        })
    
    # Calculate total messages across all rooms
    total_messages = sum(r["message_count"] for r in rooms)
    
    return {
        "person_id": person_id,
        "rooms": rooms,
        "total_rooms": len(rooms),
        "total_messages": total_messages
    }


@router.get("/{person_id}/messages", response_model=MessageListResponse)
async def get_person_messages(
    person_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    room_id: Optional[int] = Query(None, description="Filter by room ID"),
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get messages from a specific person, optionally filtered by room."""
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    query = db.query(Message).filter(Message.sender_id == person_id)
    if room_id is not None:
        query = query.filter(Message.room_id == room_id)
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


def _get_context_messages(db: Session, message_id: int, message_timestamp: datetime, count: int = 5, direction: str = "before"):
    """Get context messages before or after a given message."""
    if direction == "before":
        context = (
            db.query(Message.timestamp, Message.content, Person.display_name)
            .outerjoin(Person, Message.sender_id == Person.id)
            .filter(Message.timestamp < message_timestamp)
            .filter(Message.content.isnot(None))
            .filter(Message.content != "")
            .order_by(desc(Message.timestamp))
            .limit(count)
            .all()
        )
        # Reverse to chronological order
        return [(m.timestamp, m.display_name or "Unknown", m.content) for m in reversed(context)]
    else:
        context = (
            db.query(Message.timestamp, Message.content, Person.display_name)
            .outerjoin(Person, Message.sender_id == Person.id)
            .filter(Message.timestamp > message_timestamp)
            .filter(Message.content.isnot(None))
            .filter(Message.content != "")
            .order_by(asc(Message.timestamp))
            .limit(count)
            .all()
        )
        return [(m.timestamp, m.display_name or "Unknown", m.content) for m in context]


@router.post("/{person_id}/generate-summary")
async def generate_person_summary(
    person_id: int,
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Start AI summary generation for a person in background thread."""
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    # Check if already generating
    if person_id in _summary_status and _summary_status[person_id].get("status") == "running":
        raise HTTPException(status_code=409, detail="Summary generation already in progress")
    
    # Count messages
    message_count = (
        db.query(func.count(Message.id))
        .filter(Message.sender_id == person_id)
        .filter(Message.content.isnot(None))
        .filter(Message.content != "")
        .scalar()
    )
    
    if not message_count:
        raise HTTPException(status_code=400, detail="No messages found for this person")
    
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(status_code=500, detail="Gemini API key not configured")
    
    # Initialize status
    _summary_status[person_id] = {
        "status": "running",
        "started_at": datetime.utcnow().isoformat(),
        "message_count": message_count,
        "error": None
    }
    
    # Start generation in background thread
    thread = threading.Thread(
        target=_run_summary_generation,
        args=(person_id, person.display_name, settings.database_url, settings.gemini_api_key),
        daemon=True
    )
    thread.start()
    
    return {
        "message": "Summary generation started",
        "person_id": person_id,
        "message_count": message_count
    }


@router.get("/{person_id}/generate-summary/status")
async def get_summary_status(
    person_id: int,
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get status of summary generation for a person."""
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    status = _summary_status.get(person_id, {"status": "idle"})
    
    # Include current summary info
    return {
        **status,
        "has_summary": person.ai_summary is not None,
        "summary_generated_at": person.ai_summary_generated_at.isoformat() if person.ai_summary_generated_at else None
    }


def _get_context_messages_in_room(db: Session, room_id: int, message_timestamp: datetime, count: int = 5, direction: str = "before"):
    """Get context messages before or after a given message, within the same room."""
    if direction == "before":
        context = (
            db.query(Message.timestamp, Message.content, Person.display_name)
            .outerjoin(Person, Message.sender_id == Person.id)
            .filter(Message.room_id == room_id)
            .filter(Message.timestamp < message_timestamp)
            .filter(Message.content.isnot(None))
            .filter(Message.content != "")
            .order_by(desc(Message.timestamp))
            .limit(count)
            .all()
        )
        return [(m.timestamp, m.display_name or "Unknown", m.content) for m in reversed(context)]
    else:
        context = (
            db.query(Message.timestamp, Message.content, Person.display_name)
            .outerjoin(Person, Message.sender_id == Person.id)
            .filter(Message.room_id == room_id)
            .filter(Message.timestamp > message_timestamp)
            .filter(Message.content.isnot(None))
            .filter(Message.content != "")
            .order_by(asc(Message.timestamp))
            .limit(count)
            .all()
        )
        return [(m.timestamp, m.display_name or "Unknown", m.content) for m in context]


def _run_summary_generation(person_id: int, person_name: str, database_url: str, gemini_api_key: str):
    """Run summary generation in background thread."""
    import asyncio
    from ..services.ai import AIService
    
    db = SessionLocal()
    
    try:
        logger.info(f"Starting background summary generation for person {person_id} ({person_name})")
        
        # Fetch messages with room info
        messages = (
            db.query(Message.id, Message.timestamp, Message.content, Message.room_id, Room.name.label("room_name"))
            .outerjoin(Room, Message.room_id == Room.id)
            .filter(Message.sender_id == person_id)
            .filter(Message.content.isnot(None))
            .filter(Message.content != "")
            .order_by(asc(Message.timestamp))
            .all()
        )
        
        # Build messages with context, including room info
        messages_with_context = []
        for msg in messages:
            room_id = msg.room_id or 0
            # Get context from same room
            context_before = _get_context_messages_in_room(db, room_id, msg.timestamp, count=5, direction="before") if room_id else []
            context_after = _get_context_messages_in_room(db, room_id, msg.timestamp, count=5, direction="after") if room_id else []
            
            # Shorten room name
            room_name = msg.room_name or "Unknown Room"
            short_room_name = room_name.replace(" - Manila Dialectics Society", "")
            
            messages_with_context.append({
                "timestamp": msg.timestamp,
                "content": msg.content,
                "sender_name": person_name or "Unknown",
                "room_name": short_room_name,
                "is_target": True,
                "context_before": context_before,
                "context_after": context_after,
            })
        
        # Create AI service and generate summary
        ai_service = AIService(gemini_api_key)
        
        # Run async function in new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            summary = loop.run_until_complete(
                ai_service.generate_profile_summary_with_context(
                    person_name=person_name or "Unknown",
                    messages_with_context=messages_with_context
                )
            )
        finally:
            loop.close()
        
        # Update person record
        person = db.query(Person).filter(Person.id == person_id).first()
        if person:
            person.ai_summary = summary
            person.ai_summary_generated_at = datetime.utcnow()
            person.ai_summary_message_count = len(messages)
            db.commit()
            
            # Invalidate persona cache
            get_persona_cache().invalidate(person_id)
        
        _summary_status[person_id] = {
            "status": "completed",
            "completed_at": datetime.utcnow().isoformat(),
            "message_count": len(messages),
            "error": None
        }
        
        logger.info(f"Completed summary generation for person {person_id} ({person_name})")
        
    except Exception as e:
        logger.error(f"Error generating summary for person {person_id}: {e}")
        _summary_status[person_id] = {
            "status": "failed",
            "error": str(e),
            "completed_at": datetime.utcnow().isoformat()
        }
    
    finally:
        db.close()


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
