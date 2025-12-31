"""
Semantic Search Router - Hybrid semantic + keyword search across all entities.

Endpoints:
- GET /api/search - Search messages, discussions, people, topics
- POST /api/search/reindex - Trigger reindexing of embeddings
- GET /api/search/status - Get reindex status
- POST /api/search/embed - Embed a single entity (internal use)
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Literal, Dict, Any
from enum import Enum

from fastapi import APIRouter, Depends, Query, BackgroundTasks, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, text

from ..db import get_db, Message, Discussion, Person, Topic, Embedding
from ..auth import get_current_session
from ..services.embeddings import get_embedding_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


# =============================================================================
# Schemas
# =============================================================================

class SearchScope(str, Enum):
    ALL = "all"
    MESSAGES = "messages"
    DISCUSSIONS = "discussions"
    PEOPLE = "people"
    TOPICS = "topics"


class MatchType(str, Enum):
    HYBRID = "hybrid"
    SEMANTIC = "semantic"


class MessageResult(BaseModel):
    id: int
    content: str
    sender_id: Optional[int]
    sender_name: Optional[str]
    sender_avatar: Optional[str]
    timestamp: datetime
    score: float
    match_type: MatchType
    
    class Config:
        from_attributes = True


class DiscussionResult(BaseModel):
    id: int
    title: str
    summary: Optional[str]
    started_at: datetime
    ended_at: datetime
    message_count: int
    score: float
    match_type: MatchType
    
    class Config:
        from_attributes = True


class PersonResult(BaseModel):
    id: int
    display_name: Optional[str]
    avatar_url: Optional[str]
    ai_summary: Optional[str]
    score: float
    match_type: MatchType
    
    class Config:
        from_attributes = True


class TopicResult(BaseModel):
    id: int
    name: str
    description: Optional[str]
    color: str
    score: float
    match_type: MatchType
    
    class Config:
        from_attributes = True


class SearchCounts(BaseModel):
    messages: int
    discussions: int
    people: int
    topics: int
    total: int


class PaginationInfo(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool


class SearchResults(BaseModel):
    query: str
    results: Dict[str, List[Any]]
    counts: SearchCounts
    pagination: Dict[str, PaginationInfo]
    pagination: Dict[str, PaginationInfo]


class ReindexProgress(BaseModel):
    total: int
    completed: int


class ReindexStatus(BaseModel):
    status: Literal["idle", "running", "completed", "failed"]
    progress: Optional[Dict[str, ReindexProgress]]
    last_completed_at: Optional[datetime]
    error: Optional[str]


# =============================================================================
# State for background reindex
# =============================================================================

_reindex_state: Dict[str, Any] = {
    "status": "idle",
    "progress": None,
    "last_completed_at": None,
    "error": None,
}


# =============================================================================
# Search Endpoint
# =============================================================================

@router.get("", response_model=SearchResults)
async def search(
    q: str = Query(..., min_length=1, description="Search query"),
    scope: SearchScope = Query(SearchScope.ALL, description="Scope of search"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page per entity type"),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_session),
):
    """
    Hybrid semantic + keyword search across messages, discussions, people, and topics.
    
    Scoring:
    - If keyword match: 0.5 * semantic + 0.5 * keyword
    - If semantic only: semantic score
    - Minimum threshold: 0.3
    
    Pagination:
    - Results are paginated per entity type
    - Use page and page_size to control pagination
    """
    try:
        embedding_service = get_embedding_service()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Embedding service not initialized")
    
    # Embed the query
    try:
        query_result = embedding_service.embed_text(q)
        query_embedding = query_result.embedding
    except Exception as e:
        logger.error(f"Failed to embed query: {e}")
        raise HTTPException(status_code=500, detail="Failed to process search query")
    
    results: Dict[str, List[Any]] = {
        "messages": [],
        "discussions": [],
        "people": [],
        "topics": [],
    }
    
    # Track total counts for each entity type (before pagination)
    total_counts: Dict[str, int] = {
        "messages": 0,
        "discussions": 0,
        "people": 0,
        "topics": 0,
    }
    
    scopes_to_search = []
    if scope == SearchScope.ALL:
        scopes_to_search = ["message", "discussion", "person", "topic"]
    else:
        scope_map = {
            SearchScope.MESSAGES: "message",
            SearchScope.DISCUSSIONS: "discussion",
            SearchScope.PEOPLE: "person",
            SearchScope.TOPICS: "topic",
        }
        scopes_to_search = [scope_map[scope]]
    
    # Search each entity type
    for entity_type in scopes_to_search:
        entity_results, total = await _search_entity_type(
            db, entity_type, q, query_embedding, page, page_size
        )
        
        if entity_type == "message":
            results["messages"] = entity_results
            total_counts["messages"] = total
        elif entity_type == "discussion":
            results["discussions"] = entity_results
            total_counts["discussions"] = total
        elif entity_type == "person":
            results["people"] = entity_results
            total_counts["people"] = total
        elif entity_type == "topic":
            results["topics"] = entity_results
            total_counts["topics"] = total
    
    counts = SearchCounts(
        messages=total_counts["messages"],
        discussions=total_counts["discussions"],
        people=total_counts["people"],
        topics=total_counts["topics"],
        total=sum(total_counts.values()),
    )
    
    # Build pagination info for each entity type
    pagination: Dict[str, PaginationInfo] = {}
    for key, total in total_counts.items():
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        pagination[key] = PaginationInfo(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )
    
    return SearchResults(query=q, results=results, counts=counts, pagination=pagination)


async def _get_discussions_from_person_matches(
    db: Session,
    embedding_str: str,
    threshold: float,
) -> Dict[int, float]:
    """Find discussions by matching person embeddings, returning discussion_id -> score."""
    
    # Find people that match the query semantically
    person_query = text("""
        SELECT 
            entity_id as person_id,
            1 - (embedding <=> cast(:embedding as vector)) as semantic_score
        FROM embeddings
        WHERE entity_type = 'person'
        AND 1 - (embedding <=> cast(:embedding as vector)) >= :threshold
        ORDER BY semantic_score DESC
        LIMIT 20
    """)
    
    person_results = db.execute(
        person_query,
        {"embedding": embedding_str, "threshold": threshold}
    ).fetchall()
    
    if not person_results:
        return {}
    
    person_ids = [r[0] for r in person_results]
    person_scores = {r[0]: float(r[1]) for r in person_results}
    
    # Find discussions these people participated in
    discussion_query = text("""
        SELECT DISTINCT d.id as discussion_id, m.sender_id as person_id
        FROM discussions d
        JOIN discussion_messages dm ON dm.discussion_id = d.id
        JOIN messages m ON m.id = dm.message_id
        WHERE m.sender_id = ANY(:person_ids)
    """)
    
    discussion_results = db.execute(
        discussion_query,
        {"person_ids": person_ids}
    ).fetchall()
    
    # Map discussions to their best person match score (slightly reduced since it's indirect)
    discussion_scores: Dict[int, float] = {}
    for disc_id, person_id in discussion_results:
        person_score = person_scores.get(person_id, 0)
        # Apply a 0.85 factor since this is an indirect match via participant
        indirect_score = person_score * 0.85
        if disc_id not in discussion_scores or discussion_scores[disc_id] < indirect_score:
            discussion_scores[disc_id] = indirect_score
    
    return discussion_scores


async def _search_entity_type(
    db: Session,
    entity_type: str,
    query: str,
    query_embedding: List[float],
    page: int,
    page_size: int,
) -> tuple[List[Any], int]:
    """Search a specific entity type with hybrid scoring. Returns (results, total_count)."""
    
    SIMILARITY_THRESHOLD = 0.3
    ALPHA = 0.5  # Weight for hybrid scoring
    MAX_CANDIDATES = 500  # Max candidates to consider for scoring
    
    # Convert embedding to string format for SQL - pgvector expects '[x,y,z]' format
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    
    # Get semantic matches from embeddings table
    # Note: Use cast() syntax instead of :: to avoid parameter parsing issues
    semantic_query = text("""
        SELECT 
            entity_id,
            1 - (embedding <=> cast(:embedding as vector)) as semantic_score
        FROM embeddings
        WHERE entity_type = :entity_type
        AND 1 - (embedding <=> cast(:embedding as vector)) >= :threshold
        ORDER BY semantic_score DESC
        LIMIT :limit
    """)
    
    semantic_results = db.execute(
        semantic_query,
        {
            "embedding": embedding_str,
            "entity_type": entity_type,
            "threshold": SIMILARITY_THRESHOLD,
            "limit": MAX_CANDIDATES,  # Get many candidates for proper pagination
        }
    ).fetchall()
    
    entity_ids = [r[0] for r in semantic_results]
    semantic_scores = {r[0]: float(r[1]) for r in semantic_results}
    
    # For discussions, also find discussions via person matches
    if entity_type == "discussion":
        person_discussion_scores = await _get_discussions_from_person_matches(
            db, embedding_str, SIMILARITY_THRESHOLD
        )
        # Merge person-based discussion matches into semantic scores
        for disc_id, score in person_discussion_scores.items():
            if disc_id not in semantic_scores:
                entity_ids.append(disc_id)
                semantic_scores[disc_id] = score
            else:
                # Take max of direct discussion match vs person-based match
                semantic_scores[disc_id] = max(semantic_scores[disc_id], score)
    
    if not entity_ids:
        return [], 0
    
    # Get keyword matches for these entities
    keyword_scores = await _get_keyword_scores(db, entity_type, query, entity_ids)
    
    # Calculate final scores
    scored_results = []
    for entity_id in entity_ids:
        semantic_score = float(semantic_scores[entity_id])
        keyword_score = float(keyword_scores.get(entity_id, 0))
        
        if keyword_score > 0:
            # Hybrid score
            final_score = ALPHA * semantic_score + ALPHA * keyword_score
            match_type = MatchType.HYBRID
        else:
            # Semantic only
            final_score = semantic_score
            match_type = MatchType.SEMANTIC
        
        if final_score >= SIMILARITY_THRESHOLD:
            scored_results.append((entity_id, final_score, match_type))
    
    # Sort by score
    scored_results.sort(key=lambda x: x[1], reverse=True)
    
    # Get total count before pagination
    total_count = len(scored_results)
    
    # Apply pagination
    offset = (page - 1) * page_size
    paginated_results = scored_results[offset:offset + page_size]
    
    # Hydrate with full entity data
    hydrated = await _hydrate_results(db, entity_type, paginated_results)
    return hydrated, total_count


async def _get_keyword_scores(
    db: Session,
    entity_type: str,
    query: str,
    entity_ids: List[int],
) -> Dict[int, float]:
    """Get keyword match scores for entities."""
    
    if not entity_ids:
        return {}
    
    scores = {}
    
    if entity_type == "message":
        # Use PostgreSQL full-text search
        results = db.execute(
            text("""
                SELECT id, ts_rank(
                    to_tsvector('english', coalesce(content, '')),
                    plainto_tsquery('english', :query)
                ) as rank
                FROM messages
                WHERE id = ANY(:ids)
                AND to_tsvector('english', coalesce(content, '')) @@ plainto_tsquery('english', :query)
            """),
            {"query": query, "ids": entity_ids}
        ).fetchall()
        
        # Normalize to 0-1 range (ts_rank can exceed 1)
        if results:
            max_rank = max(r[1] for r in results) or 1
            scores = {r[0]: min(r[1] / max_rank, 1.0) for r in results}
    
    elif entity_type == "discussion":
        # ILIKE search on title + summary + participant names
        # First get title/summary matches
        results = db.execute(
            text("""
                SELECT id,
                    CASE 
                        WHEN lower(title) LIKE lower(:pattern) THEN 1.0
                        WHEN lower(coalesce(summary, '')) LIKE lower(:pattern) THEN 0.7
                        ELSE 0
                    END as score
                FROM discussions
                WHERE id = ANY(:ids)
                AND (
                    lower(title) LIKE lower(:pattern)
                    OR lower(coalesce(summary, '')) LIKE lower(:pattern)
                )
            """),
            {"pattern": f"%{query}%", "ids": entity_ids}
        ).fetchall()
        scores = {r[0]: r[1] for r in results}
        
        # Also check for participant name matches
        participant_results = db.execute(
            text("""
                SELECT DISTINCT d.id, 0.8 as score
                FROM discussions d
                JOIN discussion_messages dm ON dm.discussion_id = d.id
                JOIN messages m ON m.id = dm.message_id
                JOIN people p ON p.id = m.sender_id
                WHERE d.id = ANY(:ids)
                AND lower(coalesce(p.display_name, '')) LIKE lower(:pattern)
            """),
            {"pattern": f"%{query}%", "ids": entity_ids}
        ).fetchall()
        
        # Merge participant matches (take max score if already exists)
        for r in participant_results:
            if r[0] not in scores or scores[r[0]] < r[1]:
                scores[r[0]] = r[1]
    
    elif entity_type == "person":
        # ILIKE search on display_name + ai_summary
        results = db.execute(
            text("""
                SELECT id,
                    CASE 
                        WHEN lower(coalesce(display_name, '')) LIKE lower(:pattern) THEN 1.0
                        WHEN lower(coalesce(ai_summary, '')) LIKE lower(:pattern) THEN 0.7
                        ELSE 0
                    END as score
                FROM people
                WHERE id = ANY(:ids)
                AND (
                    lower(coalesce(display_name, '')) LIKE lower(:pattern)
                    OR lower(coalesce(ai_summary, '')) LIKE lower(:pattern)
                )
            """),
            {"pattern": f"%{query}%", "ids": entity_ids}
        ).fetchall()
        scores = {r[0]: r[1] for r in results}
    
    elif entity_type == "topic":
        # ILIKE search on name + description
        results = db.execute(
            text("""
                SELECT id,
                    CASE 
                        WHEN lower(name) LIKE lower(:pattern) THEN 1.0
                        WHEN lower(coalesce(description, '')) LIKE lower(:pattern) THEN 0.7
                        ELSE 0
                    END as score
                FROM topics
                WHERE id = ANY(:ids)
                AND (
                    lower(name) LIKE lower(:pattern)
                    OR lower(coalesce(description, '')) LIKE lower(:pattern)
                )
            """),
            {"pattern": f"%{query}%", "ids": entity_ids}
        ).fetchall()
        scores = {r[0]: r[1] for r in results}
    
    return scores


async def _hydrate_results(
    db: Session,
    entity_type: str,
    scored_results: List[tuple],
) -> List[Any]:
    """Fetch full entity data for search results."""
    
    if not scored_results:
        return []
    
    entity_ids = [r[0] for r in scored_results]
    score_map = {r[0]: (r[1], r[2]) for r in scored_results}
    
    results = []
    
    if entity_type == "message":
        messages = db.query(Message).filter(Message.id.in_(entity_ids)).all()
        msg_map = {m.id: m for m in messages}
        
        for entity_id in entity_ids:
            if entity_id not in msg_map:
                continue
            m = msg_map[entity_id]
            score, match_type = score_map[entity_id]
            results.append(MessageResult(
                id=m.id,
                content=m.content or "",
                sender_id=m.sender_id,
                sender_name=m.sender.display_name if m.sender else None,
                sender_avatar=m.sender.avatar_url if m.sender else None,
                timestamp=m.timestamp,
                score=round(score, 3),
                match_type=match_type,
            ))
    
    elif entity_type == "discussion":
        discussions = db.query(Discussion).filter(Discussion.id.in_(entity_ids)).all()
        disc_map = {d.id: d for d in discussions}
        
        for entity_id in entity_ids:
            if entity_id not in disc_map:
                continue
            d = disc_map[entity_id]
            score, match_type = score_map[entity_id]
            results.append(DiscussionResult(
                id=d.id,
                title=d.title,
                summary=d.summary,
                started_at=d.started_at,
                ended_at=d.ended_at,
                message_count=d.message_count or 0,
                score=round(score, 3),
                match_type=match_type,
            ))
    
    elif entity_type == "person":
        people = db.query(Person).filter(Person.id.in_(entity_ids)).all()
        person_map = {p.id: p for p in people}
        
        for entity_id in entity_ids:
            if entity_id not in person_map:
                continue
            p = person_map[entity_id]
            score, match_type = score_map[entity_id]
            results.append(PersonResult(
                id=p.id,
                display_name=p.display_name,
                avatar_url=p.avatar_url,
                ai_summary=p.ai_summary,
                score=round(score, 3),
                match_type=match_type,
            ))
    
    elif entity_type == "topic":
        topics = db.query(Topic).filter(Topic.id.in_(entity_ids)).all()
        topic_map = {t.id: t for t in topics}
        
        for entity_id in entity_ids:
            if entity_id not in topic_map:
                continue
            t = topic_map[entity_id]
            score, match_type = score_map[entity_id]
            results.append(TopicResult(
                id=t.id,
                name=t.name,
                description=t.description,
                color=t.color,
                score=round(score, 3),
                match_type=match_type,
            ))
    
    return results


# =============================================================================
# Reindex Endpoints
# =============================================================================

@router.get("/status", response_model=ReindexStatus)
async def get_reindex_status(
    _user: dict = Depends(get_current_session),
):
    """Get the current status of the reindexing job."""
    return ReindexStatus(
        status=_reindex_state["status"],
        progress=_reindex_state["progress"],
        last_completed_at=_reindex_state["last_completed_at"],
        error=_reindex_state["error"],
    )


@router.post("/reindex")
async def trigger_reindex(
    background_tasks: BackgroundTasks,
    scope: SearchScope = Query(SearchScope.ALL, description="Scope to reindex"),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_session),
):
    """Trigger reindexing of embeddings for the specified scope."""
    global _reindex_state
    
    if _reindex_state["status"] == "running":
        raise HTTPException(status_code=409, detail="Reindex already in progress")
    
    try:
        get_embedding_service()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Embedding service not initialized")
    
    # Reset state
    _reindex_state = {
        "status": "running",
        "progress": {},
        "last_completed_at": None,
        "error": None,
    }
    
    # Start background task
    background_tasks.add_task(_run_reindex, scope)
    
    return {"message": "Reindex started", "scope": scope.value}


async def _run_reindex(scope: SearchScope):
    """Background task to reindex embeddings."""
    global _reindex_state
    
    from ..db import SessionLocal
    
    db = SessionLocal()
    
    try:
        embedding_service = get_embedding_service()
        
        scopes_to_reindex = []
        if scope == SearchScope.ALL:
            scopes_to_reindex = ["message", "discussion", "person", "topic"]
        else:
            scope_map = {
                SearchScope.MESSAGES: "message",
                SearchScope.DISCUSSIONS: "discussion",
                SearchScope.PEOPLE: "person",
                SearchScope.TOPICS: "topic",
            }
            scopes_to_reindex = [scope_map[scope]]
        
        for entity_type in scopes_to_reindex:
            await _reindex_entity_type(db, embedding_service, entity_type)
        
        _reindex_state["status"] = "completed"
        _reindex_state["last_completed_at"] = datetime.utcnow()
        logger.info("Reindex completed successfully")
        
    except Exception as e:
        logger.error(f"Reindex failed: {e}")
        _reindex_state["status"] = "failed"
        _reindex_state["error"] = str(e)
    
    finally:
        db.close()


async def _reindex_entity_type(db: Session, embedding_service, entity_type: str):
    """Reindex all entities of a specific type."""
    global _reindex_state
    
    BATCH_SIZE = 50
    
    # Get total count
    if entity_type == "message":
        total = db.query(func.count(Message.id)).filter(
            Message.content.isnot(None),
            func.length(Message.content) >= 5
        ).scalar() or 0
    elif entity_type == "discussion":
        total = db.query(func.count(Discussion.id)).scalar() or 0
    elif entity_type == "person":
        total = db.query(func.count(Person.id)).scalar() or 0
    elif entity_type == "topic":
        total = db.query(func.count(Topic.id)).scalar() or 0
    else:
        return
    
    _reindex_state["progress"][entity_type] = {"total": total, "completed": 0}
    
    if total == 0:
        return
    
    logger.info(f"Reindexing {total} {entity_type}s...")
    
    offset = 0
    completed = 0
    
    while offset < total:
        # Fetch batch
        if entity_type == "message":
            entities = db.query(Message).filter(
                Message.content.isnot(None),
                func.length(Message.content) >= 5
            ).order_by(Message.id).offset(offset).limit(BATCH_SIZE).all()
            texts = [(e.id, embedding_service.prepare_message_content(e.content)) for e in entities]
        
        elif entity_type == "discussion":
            entities = db.query(Discussion).order_by(Discussion.id).offset(offset).limit(BATCH_SIZE).all()
            texts = [(e.id, embedding_service.prepare_discussion_content(e.title, e.summary)) for e in entities]
        
        elif entity_type == "person":
            entities = db.query(Person).order_by(Person.id).offset(offset).limit(BATCH_SIZE).all()
            texts = [(e.id, embedding_service.prepare_person_content(e.display_name or "", e.ai_summary)) for e in entities]
        
        elif entity_type == "topic":
            entities = db.query(Topic).order_by(Topic.id).offset(offset).limit(BATCH_SIZE).all()
            texts = [(e.id, embedding_service.prepare_topic_content(e.name, e.description)) for e in entities]
        
        # Filter out empty texts
        valid_texts = [(id, text) for id, text in texts if text and text.strip()]
        
        if valid_texts:
            # Embed batch
            try:
                embeddings = embedding_service.embed_batch([t[1] for t in valid_texts])
                
                # Store embeddings
                for (entity_id, _), embed_result in zip(valid_texts, embeddings):
                    existing = db.query(Embedding).filter(
                        Embedding.entity_type == entity_type,
                        Embedding.entity_id == entity_id
                    ).first()
                    
                    if existing:
                        existing.embedding = embed_result.embedding
                        existing.content_hash = embed_result.content_hash
                        existing.created_at = datetime.utcnow()
                    else:
                        db.add(Embedding(
                            entity_type=entity_type,
                            entity_id=entity_id,
                            embedding=embed_result.embedding,
                            content_hash=embed_result.content_hash,
                        ))
                
                db.commit()
                
            except Exception as e:
                logger.error(f"Error embedding batch for {entity_type}: {e}")
                db.rollback()
                raise
        
        completed += len(entities)
        offset += BATCH_SIZE
        _reindex_state["progress"][entity_type]["completed"] = completed
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(0.1)
    
    logger.info(f"Completed reindexing {completed} {entity_type}s")


# =============================================================================
# Single Entity Embedding (for real-time updates)
# =============================================================================

@router.post("/embed")
async def embed_entity(
    entity_type: str = Query(..., description="Entity type: message, discussion, person, topic"),
    entity_id: int = Query(..., description="Entity ID"),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_session),
):
    """Embed a single entity. Used for real-time updates when new content is added."""
    
    try:
        embedding_service = get_embedding_service()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Embedding service not initialized")
    
    # Get entity and prepare content
    content = None
    
    if entity_type == "message":
        entity = db.query(Message).filter(Message.id == entity_id).first()
        if entity:
            content = embedding_service.prepare_message_content(entity.content or "")
    
    elif entity_type == "discussion":
        entity = db.query(Discussion).filter(Discussion.id == entity_id).first()
        if entity:
            content = embedding_service.prepare_discussion_content(entity.title, entity.summary)
    
    elif entity_type == "person":
        entity = db.query(Person).filter(Person.id == entity_id).first()
        if entity:
            content = embedding_service.prepare_person_content(entity.display_name or "", entity.ai_summary)
    
    elif entity_type == "topic":
        entity = db.query(Topic).filter(Topic.id == entity_id).first()
        if entity:
            content = embedding_service.prepare_topic_content(entity.name, entity.description)
    
    else:
        raise HTTPException(status_code=400, detail=f"Invalid entity type: {entity_type}")
    
    if not content:
        raise HTTPException(status_code=404, detail=f"{entity_type} {entity_id} not found or has no content")
    
    # Check if content has changed
    existing = db.query(Embedding).filter(
        Embedding.entity_type == entity_type,
        Embedding.entity_id == entity_id
    ).first()
    
    content_hash = embedding_service.get_content_hash(content)
    
    if existing and existing.content_hash == content_hash:
        return {"message": "Content unchanged, skipping embedding", "entity_type": entity_type, "entity_id": entity_id}
    
    # Embed
    try:
        result = embedding_service.embed_text(content)
        
        if existing:
            existing.embedding = result.embedding
            existing.content_hash = result.content_hash
            existing.created_at = datetime.utcnow()
        else:
            db.add(Embedding(
                entity_type=entity_type,
                entity_id=entity_id,
                embedding=result.embedding,
                content_hash=result.content_hash,
            ))
        
        db.commit()
        
        return {"message": "Embedded successfully", "entity_type": entity_type, "entity_id": entity_id}
        
    except Exception as e:
        logger.error(f"Error embedding {entity_type} {entity_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
