"""
Discussions Router - API endpoints for AI-detected discussions.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from ..db import (
    get_db, 
    Message, 
    Person,
    Discussion, 
    DiscussionMessage, 
    DiscussionAnalysisRun
)
from ..auth import get_current_session
from ..config import get_settings
from ..schemas.discussion import (
    DiscussionBrief,
    DiscussionFull,
    DiscussionListResponse,
    DiscussionMessageResponse,
    AnalysisStatusResponse,
    AnalyzeResponse,
    PersonBrief,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/discussions", tags=["discussions"])

# Track if analysis is currently running
_analysis_running = False


def run_analysis_sync(run_id: int, db_url: str, api_key: str):
    """Background task to run discussion analysis in a separate thread."""
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_analysis_async(run_id, db_url, api_key))
    finally:
        loop.close()


async def _run_analysis_async(run_id: int, db_url: str, api_key: str):
    """Actual analysis logic."""
    global _analysis_running
    
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from ..services.discussions import DiscussionAnalyzer
    
    engine = create_engine(db_url, pool_size=1, max_overflow=0)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        _analysis_running = True
        
        # Get the run record
        run = db.query(DiscussionAnalysisRun).filter(DiscussionAnalysisRun.id == run_id).first()
        if not run:
            logger.error(f"Analysis run {run_id} not found")
            return
        
        # Delete any previous discussions (replace mode)
        previous_runs = db.query(DiscussionAnalysisRun).filter(
            DiscussionAnalysisRun.id != run_id
        ).all()
        for prev_run in previous_runs:
            db.delete(prev_run)
        db.commit()
        
        # Create analyzer with run_id so it can write to DB directly
        analyzer = DiscussionAnalyzer(api_key=api_key, db_session=db, run_id=run_id)
        
        # Progress callback
        def update_progress(windows_done: int, total: int):
            run.windows_processed = windows_done
            run.total_windows = total
            run.discussions_found = len(analyzer.state.active_discussions)
            db.commit()
        
        # Run analysis (writes to DB incrementally)
        result = await analyzer.analyze_all_messages(
            update_progress_callback=update_progress
        )
        
        # Update participant counts for all discussions
        all_discussions = db.query(Discussion).filter(
            Discussion.analysis_run_id == run_id
        ).all()
        
        for discussion in all_discussions:
            # Count unique participants
            participant_count = db.query(func.count(func.distinct(Message.sender_id))).join(
                DiscussionMessage, Message.id == DiscussionMessage.message_id
            ).filter(
                DiscussionMessage.discussion_id == discussion.id
            ).scalar() or 0
            discussion.participant_count = participant_count
        
        db.commit()
        
        # Generate summaries for each discussion
        logger.info("Generating discussion summaries...")
        for discussion in all_discussions:
            messages = (
                db.query(Message)
                .join(DiscussionMessage)
                .filter(DiscussionMessage.discussion_id == discussion.id)
                .order_by(Message.timestamp)
                .all()
            )
            
            if messages:
                summary = await analyzer.generate_discussion_summary(
                    discussion.id,
                    discussion.title,
                    messages
                )
                discussion.summary = summary
        
        db.commit()
        
        # Update run status
        run.status = "completed"
        run.completed_at = datetime.utcnow()
        run.discussions_found = result.get("discussions_found", 0)
        run.tokens_used = result.get("total_tokens", 0)
        db.commit()
        
        logger.info(f"Analysis complete: {result.get('discussions_found', 0)} discussions created")
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        run = db.query(DiscussionAnalysisRun).filter(DiscussionAnalysisRun.id == run_id).first()
        if run:
            run.status = "failed"
            run.error_message = str(e)
            run.completed_at = datetime.utcnow()
            db.commit()
    
    finally:
        _analysis_running = False
        db.close()


@router.post("/analyze", response_model=AnalyzeResponse)
async def start_analysis(
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Start a new discussion analysis. Replaces any previous analysis."""
    import threading
    global _analysis_running
    
    if _analysis_running:
        raise HTTPException(status_code=409, detail="Analysis already running")
    
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(status_code=500, detail="Gemini API key not configured")
    
    # Create a new analysis run
    run = DiscussionAnalysisRun(
        status="running",
        started_at=datetime.utcnow()
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    
    # Start in a separate thread to not block the main event loop
    thread = threading.Thread(
        target=run_analysis_sync,
        args=(run.id, settings.database_url, settings.gemini_api_key),
        daemon=True
    )
    thread.start()
    
    return AnalyzeResponse(
        message="Analysis started",
        run_id=run.id
    )


@router.get("/analysis-status", response_model=AnalysisStatusResponse)
async def get_analysis_status(
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get the status of the latest analysis run."""
    run = db.query(DiscussionAnalysisRun).order_by(desc(DiscussionAnalysisRun.id)).first()
    
    if not run:
        return AnalysisStatusResponse(status="none")
    
    return AnalysisStatusResponse(
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        windows_processed=run.windows_processed or 0,
        total_windows=run.total_windows or 0,
        discussions_found=run.discussions_found or 0,
        tokens_used=run.tokens_used or 0,
        error_message=run.error_message
    )


@router.get("", response_model=DiscussionListResponse)
async def list_discussions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """List all detected discussions."""
    total = db.query(func.count(Discussion.id)).scalar() or 0
    
    offset = (page - 1) * page_size
    discussions = (
        db.query(Discussion)
        .order_by(desc(Discussion.started_at))
        .offset(offset)
        .limit(page_size)
        .all()
    )
    
    discussion_briefs = [
        DiscussionBrief(
            id=d.id,
            title=d.title,
            summary=d.summary,
            started_at=d.started_at,
            ended_at=d.ended_at,
            message_count=d.message_count,
            participant_count=d.participant_count
        )
        for d in discussions
    ]
    
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    return DiscussionListResponse(
        discussions=discussion_briefs,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{discussion_id}", response_model=DiscussionFull)
async def get_discussion(
    discussion_id: int,
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get a discussion with all its messages."""
    discussion = db.query(Discussion).filter(Discussion.id == discussion_id).first()
    
    if not discussion:
        raise HTTPException(status_code=404, detail="Discussion not found")
    
    # Get messages with confidence scores
    message_data = (
        db.query(Message, DiscussionMessage.confidence, Person)
        .join(DiscussionMessage, Message.id == DiscussionMessage.message_id)
        .outerjoin(Person, Message.sender_id == Person.id)
        .filter(DiscussionMessage.discussion_id == discussion_id)
        .order_by(Message.timestamp)
        .all()
    )
    
    messages = []
    for msg, confidence, sender in message_data:
        sender_brief = None
        if sender:
            sender_brief = PersonBrief(
                id=sender.id,
                display_name=sender.display_name,
                avatar_url=sender.avatar_url
            )
        
        messages.append(DiscussionMessageResponse(
            id=msg.id,
            content=msg.content,
            timestamp=msg.timestamp,
            sender=sender_brief,
            confidence=confidence
        ))
    
    return DiscussionFull(
        id=discussion.id,
        title=discussion.title,
        summary=discussion.summary,
        started_at=discussion.started_at,
        ended_at=discussion.ended_at,
        message_count=discussion.message_count,
        participant_count=discussion.participant_count,
        messages=messages
    )
