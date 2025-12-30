from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, timedelta

from ..db import get_db, Message, Person
from ..auth import get_current_session
from ..schemas.stats import StatsResponse, ActivityDataPoint

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", response_model=StatsResponse)
async def get_stats(
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get dashboard statistics."""
    # Total messages
    total_messages = db.query(func.count(Message.id)).scalar() or 0
    
    # Total people
    total_people = db.query(func.count(Person.id)).scalar() or 0
    
    # Total threads (messages that have at least one reply)
    total_threads = (
        db.query(func.count(func.distinct(Message.reply_to_message_id)))
        .filter(Message.reply_to_message_id.isnot(None))
        .scalar() or 0
    )
    
    # Activity for last 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    activity_query = (
        db.query(
            func.date(Message.timestamp).label("date"),
            func.count(Message.id).label("count")
        )
        .filter(Message.timestamp >= thirty_days_ago)
        .group_by(func.date(Message.timestamp))
        .order_by(func.date(Message.timestamp))
        .all()
    )
    
    activity = [
        ActivityDataPoint(date=row.date, count=row.count)
        for row in activity_query
    ]
    
    return StatsResponse(
        total_messages=total_messages,
        total_threads=total_threads,
        total_people=total_people,
        activity=activity
    )


@router.get("/recent")
async def get_recent_activity(
    limit: int = 10,
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get recent messages for the dashboard."""
    from ..schemas.message import MessageResponse, PersonBrief
    
    messages = (
        db.query(Message)
        .order_by(desc(Message.timestamp))
        .limit(limit)
        .all()
    )
    
    result = []
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
        
        result.append(MessageResponse(
            id=msg.id,
            content=msg.content,
            timestamp=msg.timestamp,
            sender=sender_brief,
            reply_to_message_id=msg.reply_to_message_id,
            reply_to_sender=reply_to_sender
        ))
    
    return result
