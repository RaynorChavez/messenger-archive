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
    DiscussionAnalysisRun,
    Topic,
    DiscussionTopic,
    TopicClassificationRun,
)
from ..auth import get_current_session
from ..config import get_settings
from ..schemas.discussion import (
    DiscussionBrief,
    DiscussionBriefWithTopics,
    DiscussionFull,
    DiscussionListResponse,
    DiscussionMessageResponse,
    AnalysisStatusResponse,
    AnalyzeResponse,
    PersonBrief,
    TopicBrief,
    TopicListResponse,
    TopicClassificationStatusResponse,
    ClassifyTopicsResponse,
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
    """Start a new discussion analysis. Replaces any previous analysis.
    
    If a previous analysis was interrupted (stale), this will start fresh.
    """
    import threading
    from datetime import timezone, timedelta
    global _analysis_running
    
    if _analysis_running:
        raise HTTPException(status_code=409, detail="Analysis already running")
    
    # Check for stale runs and mark them as failed
    stale_run = db.query(DiscussionAnalysisRun).filter(
        DiscussionAnalysisRun.status == "running"
    ).first()
    
    if stale_run and stale_run.started_at:
        now = datetime.now(timezone.utc)
        started = stale_run.started_at.replace(tzinfo=timezone.utc) if stale_run.started_at.tzinfo is None else stale_run.started_at
        if now - started > timedelta(minutes=2):
            # Mark stale run as failed
            stale_run.status = "failed"
            stale_run.error_message = f"Interrupted - processed {stale_run.windows_processed or 0}/{stale_run.total_windows or 0} windows before restart"
            stale_run.completed_at = datetime.utcnow()
            db.commit()
            logger.info(f"Marked stale analysis run {stale_run.id} as failed")
    
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
    """Get the status of the latest analysis run.
    
    Detects stale 'running' states when the analysis thread died (e.g., container restart).
    A run is considered stale if it's been 'running' for more than 10 minutes without progress.
    """
    run = db.query(DiscussionAnalysisRun).order_by(desc(DiscussionAnalysisRun.id)).first()
    
    if not run:
        return AnalysisStatusResponse(status="none")
    
    status = run.status
    error_message = run.error_message
    
    # Detect stale 'running' status - if not actually running in memory
    if status == "running" and not _analysis_running:
        # Check if started more than 2 minutes ago - indicates orphaned state
        if run.started_at:
            from datetime import timezone, timedelta
            now = datetime.now(timezone.utc)
            started = run.started_at.replace(tzinfo=timezone.utc) if run.started_at.tzinfo is None else run.started_at
            if now - started > timedelta(minutes=2):
                status = "stale"
                error_message = f"Analysis was interrupted (processed {run.windows_processed or 0}/{run.total_windows or 0} windows). Click 'Analyze' to restart from the beginning."
    
    return AnalysisStatusResponse(
        status=status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        windows_processed=run.windows_processed or 0,
        total_windows=run.total_windows or 0,
        discussions_found=run.discussions_found or 0,
        tokens_used=run.tokens_used or 0,
        error_message=error_message
    )


@router.get("/timeline")
async def get_timeline(
    topic_id: Optional[int] = Query(None, description="Filter by topic ID"),
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get discussion counts grouped by date for timeline display."""
    from sqlalchemy import cast, Date
    
    # Base query - group by date
    query = db.query(
        cast(Discussion.started_at, Date).label("date"),
        func.count(Discussion.id).label("count")
    )
    
    # Apply topic filter if specified
    if topic_id is not None:
        query = query.join(DiscussionTopic).filter(DiscussionTopic.topic_id == topic_id)
    
    # Group by date and order descending
    results = (
        query
        .group_by(cast(Discussion.started_at, Date))
        .order_by(desc(cast(Discussion.started_at, Date)))
        .all()
    )
    
    # Get total count
    count_query = db.query(func.count(Discussion.id))
    if topic_id is not None:
        count_query = count_query.join(DiscussionTopic).filter(DiscussionTopic.topic_id == topic_id)
    total = count_query.scalar() or 0
    
    return {
        "timeline": [
            {"date": str(r.date), "count": r.count}
            for r in results
        ],
        "total": total
    }


@router.get("", response_model=DiscussionListResponse)
async def list_discussions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    topic_id: Optional[int] = Query(None, description="Filter by topic ID"),
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """List all detected discussions, optionally filtered by topic."""
    # Base query
    query = db.query(Discussion)
    count_query = db.query(func.count(Discussion.id))
    
    # Apply topic filter if specified
    if topic_id is not None:
        query = query.join(DiscussionTopic).filter(DiscussionTopic.topic_id == topic_id)
        count_query = count_query.join(DiscussionTopic).filter(DiscussionTopic.topic_id == topic_id)
    
    total = count_query.scalar() or 0
    
    offset = (page - 1) * page_size
    discussions = (
        query
        .order_by(desc(Discussion.started_at))
        .offset(offset)
        .limit(page_size)
        .all()
    )
    
    # Get topics for each discussion
    discussion_briefs = []
    for d in discussions:
        # Fetch topics for this discussion
        topics = db.query(Topic).join(DiscussionTopic).filter(
            DiscussionTopic.discussion_id == d.id
        ).all()
        
        topic_briefs = [
            TopicBrief(
                id=t.id,
                name=t.name,
                description=t.description,
                color=t.color,
                discussion_count=0  # Not needed for inline display
            )
            for t in topics
        ]
        
        discussion_briefs.append(
            DiscussionBriefWithTopics(
                id=d.id,
                title=d.title,
                summary=d.summary,
                started_at=d.started_at,
                ended_at=d.ended_at,
                message_count=d.message_count,
                participant_count=d.participant_count,
                topics=topic_briefs
            )
        )
    
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


# =============================================================================
# Topic Classification Endpoints
# =============================================================================

# Track if topic classification is running
_topic_classification_running = False


def run_topic_classification_sync(run_id: int, db_url: str, api_key: str):
    """Background task to run topic classification in a separate thread."""
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_topic_classification_async(run_id, db_url, api_key))
    finally:
        loop.close()


async def _run_topic_classification_async(run_id: int, db_url: str, api_key: str):
    """Actual topic classification logic."""
    global _topic_classification_running
    
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from ..services.discussions import DiscussionAnalyzer
    
    engine = create_engine(db_url, pool_size=1, max_overflow=0)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        _topic_classification_running = True
        
        # Get the run record
        run = db.query(TopicClassificationRun).filter(TopicClassificationRun.id == run_id).first()
        if not run:
            logger.error(f"Topic classification run {run_id} not found")
            return
        
        # Create analyzer (run_id=0 since we're not doing discussion analysis)
        analyzer = DiscussionAnalyzer(api_key=api_key, db_session=db, run_id=0)
        
        # Run classification
        result = await analyzer.classify_topics()
        
        # Update run status
        run.status = "completed"
        run.completed_at = datetime.utcnow()
        run.topics_created = result.get("topics_created", 0)
        run.discussions_classified = result.get("discussions_classified", 0)
        db.commit()
        
        logger.info(f"Topic classification complete: {run.topics_created} topics, {run.discussions_classified} discussions")
        
    except Exception as e:
        logger.error(f"Topic classification failed: {e}")
        run = db.query(TopicClassificationRun).filter(TopicClassificationRun.id == run_id).first()
        if run:
            run.status = "failed"
            run.error_message = str(e)
            run.completed_at = datetime.utcnow()
            db.commit()
    
    finally:
        _topic_classification_running = False
        db.close()


@router.get("/topics/list", response_model=TopicListResponse)
async def list_topics(
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """List all topics with discussion counts."""
    topics = db.query(Topic).all()
    
    topic_briefs = []
    for topic in topics:
        discussion_count = db.query(func.count(DiscussionTopic.discussion_id)).filter(
            DiscussionTopic.topic_id == topic.id
        ).scalar() or 0
        
        topic_briefs.append(TopicBrief(
            id=topic.id,
            name=topic.name,
            description=topic.description,
            color=topic.color,
            discussion_count=discussion_count
        ))
    
    return TopicListResponse(topics=topic_briefs)


@router.post("/classify-topics", response_model=ClassifyTopicsResponse)
async def start_topic_classification(
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Start topic classification for all discussions."""
    import threading
    global _topic_classification_running
    
    if _topic_classification_running:
        raise HTTPException(status_code=409, detail="Topic classification already running")
    
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(status_code=500, detail="Gemini API key not configured")
    
    # Create a new classification run
    run = TopicClassificationRun(
        status="running",
        started_at=datetime.utcnow()
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    
    # Start in a separate thread
    thread = threading.Thread(
        target=run_topic_classification_sync,
        args=(run.id, settings.database_url, settings.gemini_api_key),
        daemon=True
    )
    thread.start()
    
    return ClassifyTopicsResponse(
        message="Topic classification started",
        run_id=run.id
    )


@router.get("/classify-topics/status", response_model=TopicClassificationStatusResponse)
async def get_topic_classification_status(
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Get the status of topic classification."""
    # Get the most recent run
    run = db.query(TopicClassificationRun).order_by(desc(TopicClassificationRun.id)).first()
    
    if not run:
        return TopicClassificationStatusResponse(
            status="none",
            topics_created=0,
            discussions_classified=0
        )
    
    return TopicClassificationStatusResponse(
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        topics_created=run.topics_created or 0,
        discussions_classified=run.discussions_classified or 0,
        error_message=run.error_message
    )
