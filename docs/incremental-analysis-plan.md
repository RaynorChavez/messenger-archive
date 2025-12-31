# Incremental Discussion Analysis - Implementation Plan

## Overview

Currently, every analysis run processes ALL messages from scratch, deleting previous discussions. This costs ~$3.50 for ~6,000 messages. As the archive grows, this becomes unsustainable.

**Goal:** Add an incremental mode that only processes new messages since the last completed run, with context overlap for continuity. Expected cost reduction: 90-95%.

---

## Current Architecture

### Database Schema
```
discussion_analysis_runs:
  - id, started_at, completed_at, status, windows_processed, 
  - total_windows, discussions_found, tokens_used, error_message

discussions:
  - id, analysis_run_id, title, summary, started_at, ended_at, 
  - message_count, participant_count, created_at
```

### Analysis Flow (Current)
1. `POST /api/discussions/analyze` creates a new `DiscussionAnalysisRun`
2. **Deletes ALL previous runs and their discussions** (cascade delete)
3. Fetches ALL messages ordered by timestamp
4. Processes in windows of 30 messages (20 net, 10 overlap)
5. For each window:
   - Sends messages + active discussions to Gemini
   - AI classifies messages, creates new discussions, ends discussions
   - State is updated incrementally in DB
6. Generates summaries for all discussions
7. Marks run as completed

### Key State Tracking
- `AnalysisState`: tracks active discussions, temp_id mappings, tokens used
- `ActiveDiscussion`: tracks id, title, message_ids, timestamps, dormancy status
- Dormancy after 5 windows of inactivity (discussion hidden from AI but not deleted)

---

## Proposed Changes

### 1. Database Schema Changes

```sql
ALTER TABLE discussion_analysis_runs ADD COLUMN 
  mode VARCHAR(20) DEFAULT 'full',              -- 'full' or 'incremental'
  start_message_id INTEGER,                      -- First new message analyzed (NULL for full)
  end_message_id INTEGER,                        -- Last message analyzed
  context_start_message_id INTEGER,              -- Start of context window (for incremental)
  new_messages_count INTEGER DEFAULT 0,          -- Count of new messages processed
  context_messages_count INTEGER DEFAULT 0;      -- Count of context messages loaded
```

**Why these fields:**
- `mode`: Distinguishes run type for status display and logic
- `start_message_id`: For incremental, the first NEW message (after context)
- `end_message_id`: Last message processed (used as cutoff for next incremental run)
- `context_start_message_id`: For incremental, where context loading began
- `new_messages_count` / `context_messages_count`: For accurate progress display

### 2. Incremental Analysis Logic

#### 2.1 Finding the Cutoff Point

```python
def get_incremental_cutoff(db: Session) -> Optional[int]:
    """Find the message ID to start from for incremental analysis."""
    # Get last COMPLETED run (not failed or running)
    last_run = db.query(DiscussionAnalysisRun).filter(
        DiscussionAnalysisRun.status == "completed"
    ).order_by(desc(DiscussionAnalysisRun.completed_at)).first()
    
    if not last_run or not last_run.end_message_id:
        return None  # No valid previous run, must do full
    
    return last_run.end_message_id
```

#### 2.2 Loading Context for Continuity

For incremental mode, we need context to:
1. Understand active discussions from the previous run
2. Give the AI continuity for classification

**Context Strategy:**
- Load 4 windows worth of messages BEFORE the cutoff (~120 messages)
- These are **read-only context** - already classified, not re-processed
- Load the state of active discussions from the previous run

```python
CONTEXT_WINDOWS = 4  # ~120 messages of context
WINDOW_SIZE = 30
CONTEXT_MESSAGE_COUNT = CONTEXT_WINDOWS * WINDOW_SIZE

def load_incremental_context(db: Session, cutoff_message_id: int) -> Tuple[List[Message], Dict]:
    """Load context messages and active discussion state for incremental run."""
    
    # Get the message with this ID to find its position
    cutoff_msg = db.query(Message).filter(Message.id == cutoff_message_id).first()
    if not cutoff_msg:
        raise ValueError(f"Cutoff message {cutoff_message_id} not found")
    
    # Load context messages (before cutoff)
    context_messages = db.query(Message).filter(
        Message.timestamp <= cutoff_msg.timestamp,
        Message.content.isnot(None),
        Message.content != ""
    ).order_by(desc(Message.timestamp)).limit(CONTEXT_MESSAGE_COUNT).all()
    
    # Reverse to chronological order
    context_messages = list(reversed(context_messages))
    
    # Load active discussions that weren't ended
    active_discussions = db.query(Discussion).filter(
        Discussion.ended_at >= cutoff_msg.timestamp - timedelta(hours=48)
        # Only discussions that ended within 48h of cutoff are potentially still active
    ).all()
    
    return context_messages, active_discussions
```

#### 2.3 Reconstructing State from Previous Run

For incremental mode, we need to rebuild `AnalysisState` from the database:

```python
def rebuild_state_from_db(
    db: Session, 
    active_discussions: List[Discussion],
    context_messages: List[Message]
) -> AnalysisState:
    """Rebuild AnalysisState from previous run's discussions."""
    
    state = AnalysisState()
    
    for disc in active_discussions:
        # Get message IDs for this discussion
        msg_ids = [dm.message_id for dm in disc.message_links]
        
        # Get topic keywords (regenerate from title if not stored)
        # Note: We might want to store these in DB in future
        keywords = generate_topic_keywords(disc.title)
        
        # Get recent participants
        recent_msgs = db.query(Message).filter(
            Message.id.in_(msg_ids)
        ).order_by(desc(Message.timestamp)).limit(10).all()
        
        participants = list(set(
            m.sender.display_name for m in recent_msgs 
            if m.sender and m.sender.display_name
        ))[:5]
        
        state.active_discussions[disc.id] = ActiveDiscussion(
            id=disc.id,
            title=disc.title,
            temp_id=f"existing_{disc.id}",
            message_ids=msg_ids,
            started_at=disc.started_at,
            ended_at=disc.ended_at,
            last_active_window=0,  # Will be updated as we process context
            dormant=False,  # Assume not dormant initially
            topic_keywords=keywords,
            recent_participants=participants
        )
        state.temp_id_to_db_id[f"existing_{disc.id}"] = disc.id
    
    return state
```

#### 2.4 Processing Context Windows (Read-Only)

Before processing new messages, we run context messages through the AI to:
1. Let it "see" recent conversation
2. Update dormancy states appropriately
3. **BUT NOT modify the database** - context is read-only

```python
async def process_context_windows(
    self, 
    context_messages: List[Message]
) -> None:
    """Process context messages to warm up AI state. Read-only - no DB writes."""
    
    # Process context in windows, but don't save assignments
    for window_start in range(0, len(context_messages), self.WINDOW_SIZE - self.OVERLAP_SIZE):
        window_end = min(window_start + self.WINDOW_SIZE, len(context_messages))
        window_messages = context_messages[window_start:window_end]
        
        self.state.current_window += 1
        
        # Process window (updates in-memory state only)
        response = self._process_window(window_messages)
        
        if response:
            # Update state but DON'T write to DB
            self._update_state_from_response_readonly(response, window_messages)
```

#### 2.5 Modified analyze_all_messages

```python
async def analyze_messages(
    self,
    mode: str = "incremental",  # or "full"
    update_progress_callback=None
) -> Dict[str, Any]:
    """Run analysis. Supports full or incremental mode."""
    
    if mode == "full":
        # Existing behavior - process all messages
        return await self._analyze_full(update_progress_callback)
    
    # Incremental mode
    cutoff_id = get_incremental_cutoff(self.db)
    
    if cutoff_id is None:
        logger.info("No previous completed run, falling back to full analysis")
        return await self._analyze_full(update_progress_callback)
    
    # Load context and rebuild state
    context_messages, active_discussions = load_incremental_context(self.db, cutoff_id)
    self.state = rebuild_state_from_db(self.db, active_discussions, context_messages)
    
    # Get new messages (after cutoff)
    new_messages = self.db.query(Message).filter(
        Message.id > cutoff_id,
        Message.content.isnot(None),
        Message.content != ""
    ).order_by(asc(Message.timestamp)).all()
    
    if not new_messages:
        return {"discussions_found": 0, "new_messages": 0, "message": "No new messages"}
    
    logger.info(f"Incremental analysis: {len(context_messages)} context, {len(new_messages)} new")
    
    # Process context windows (read-only, warms up state)
    await self.process_context_windows(context_messages)
    
    # Process new messages (writes to DB)
    return await self._analyze_new_messages(new_messages, update_progress_callback)
```

### 3. API Changes

#### 3.1 Analyze Endpoint

```python
@router.post("/analyze")
async def start_analysis(
    mode: str = Query("incremental", description="'incremental' or 'full'"),
    db: Session = Depends(get_db),
    session: str = Depends(get_current_session),
):
    """Start discussion analysis.
    
    - incremental (default): Only process new messages since last completed run
    - full: Delete all discussions and re-analyze from scratch
    """
    # For full mode, warn about cost
    # For incremental mode, calculate and show new message count
```

#### 3.2 Status Endpoint

Add new fields to `AnalysisStatusResponse`:

```python
class AnalysisStatusResponse(BaseModel):
    status: str  # none, running, completed, failed, stale
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    windows_processed: int
    total_windows: int
    discussions_found: int
    tokens_used: int
    error_message: Optional[str]
    # New fields for incremental
    mode: Optional[str]  # "full" or "incremental"
    new_messages_count: Optional[int]
    context_messages_count: Optional[int]
```

#### 3.3 Pre-flight Check Endpoint (Optional)

```python
@router.get("/analyze/preview")
async def preview_analysis(
    mode: str = Query("incremental"),
    db: Session = Depends(get_db)
):
    """Preview what an analysis run would process without starting it."""
    
    if mode == "incremental":
        cutoff_id = get_incremental_cutoff(db)
        if cutoff_id is None:
            return {"mode": "full", "reason": "No previous completed run"}
        
        new_count = db.query(func.count(Message.id)).filter(
            Message.id > cutoff_id,
            Message.content.isnot(None)
        ).scalar()
        
        return {
            "mode": "incremental",
            "new_messages": new_count,
            "context_messages": min(120, new_count),  # Estimate
            "estimated_cost": estimate_cost(new_count + 120)
        }
    else:
        total = db.query(func.count(Message.id)).filter(
            Message.content.isnot(None)
        ).scalar()
        return {
            "mode": "full",
            "total_messages": total,
            "estimated_cost": estimate_cost(total)
        }
```

### 4. Frontend Changes

#### 4.1 Discussions Page Header

Current:
```
[Analyze] button
```

Proposed:
```
[Analyze (47 new)] primary button  |  [Full Re-analysis] secondary/dropdown
```

If no new messages:
```
[Analysis up to date] disabled  |  [Full Re-analysis] 
```

#### 4.2 Progress Display

Current:
```
Analyzing: 45/200 windows | 23 discussions found
```

Proposed for incremental:
```
Analyzing 47 new messages (with 120 context)
Progress: 5/8 windows | 3 new discussions found
```

#### 4.3 Confirmation for Full Re-analysis

When clicking "Full Re-analysis":
```
Warning: This will delete all 183 existing discussions and 
re-analyze 6,234 messages from scratch.

Estimated cost: ~$3.50
Time: ~10 minutes

[Cancel] [Proceed]
```

### 5. Edge Cases

#### 5.1 Discussion Spans Old and New Messages

**Scenario:** A discussion was active at the end of the last run and continues with new messages.

**Solution:** Context windows let the AI see the discussion is active. When processing new messages, it can assign them to the existing discussion (by DB ID).

#### 5.2 Long Gap Between Runs

**Scenario:** 2 weeks pass between runs, 1000+ new messages.

**Solution:** Still works - just takes longer. Context ensures continuity for any discussions that were active at the cutoff.

#### 5.3 Previous Run Failed

**Scenario:** Last run failed after processing 50% of messages.

**Solution:** We only use COMPLETED runs for the cutoff. Failed runs are ignored. User can:
- Retry incremental (uses last completed run's cutoff)
- Do a full re-analysis

#### 5.4 First Run Ever

**Scenario:** No previous completed runs exist.

**Solution:** Incremental mode auto-falls back to full mode.

#### 5.5 Messages Deleted/Modified

**Scenario:** Messages from before the cutoff were deleted or edited.

**Solution:** This is rare and we don't handle it automatically. User can do a full re-analysis if needed.

#### 5.6 Container Restart During Incremental

**Scenario:** Container restarts mid-analysis.

**Solution:** Same as current - run is marked stale, user can retry. Incremental is more resilient because less work is wasted.

### 6. Data Integrity Considerations

#### 6.1 Discussion IDs Must Be Stable

Incremental mode references existing discussion IDs. Important:
- Never delete discussions unless doing full re-analysis
- `analysis_run_id` foreign key must be handled carefully

**Proposed change:** For incremental runs, keep `analysis_run_id` as NULL or set to the original run that created the discussion. Only full runs own discussions via cascade delete.

#### 6.2 Summaries for Extended Discussions

When a discussion gets new messages in an incremental run:
- Re-generate summary to include new messages
- Track which discussions were extended

```python
extended_discussion_ids = set()  # Track during processing

# After processing
for disc_id in extended_discussion_ids:
    discussion = db.query(Discussion).filter(Discussion.id == disc_id).first()
    if discussion:
        messages = get_discussion_messages(db, disc_id)
        discussion.summary = await generate_summary(discussion.title, messages)
```

### 7. Migration Plan

1. **Phase 1:** Add new columns to `discussion_analysis_runs` (backward compatible)
2. **Phase 2:** Update analyzer to support mode parameter (default: full for safety)
3. **Phase 3:** Update API to accept mode parameter
4. **Phase 4:** Update frontend with new UI
5. **Phase 5:** Change default to incremental

### 8. Testing Strategy

1. **Unit tests:**
   - `get_incremental_cutoff` with various scenarios
   - `rebuild_state_from_db` state reconstruction
   - `process_context_windows` read-only behavior

2. **Integration tests:**
   - Full analysis → Incremental analysis flow
   - Incremental with no new messages
   - Incremental fallback to full
   - Discussion extension across runs

3. **Manual testing:**
   - Run full analysis
   - Add a few messages
   - Run incremental, verify:
     - Old discussions preserved
     - New messages classified correctly
     - Extended discussions have updated summaries

---

## File Changes Summary

| File | Changes |
|------|---------|
| `api/src/db.py` | Add new columns to `DiscussionAnalysisRun` model |
| `scripts/init-db.sql` | Add new columns (for fresh installs) |
| `scripts/migrate-incremental.sql` | Migration script for existing DBs |
| `api/src/services/discussions.py` | Add incremental analysis logic |
| `api/src/routers/discussions.py` | Add mode parameter, update status response |
| `api/src/schemas/discussion.py` | Update status schema with new fields |
| `web/src/lib/api.ts` | Update types, add preview endpoint |
| `web/src/app/discussions/page.tsx` | Update UI for incremental/full modes |

---

## Cost-Benefit Analysis

| Scenario | Messages | Windows | Est. Cost | Time |
|----------|----------|---------|-----------|------|
| Full (6,000) | 6,000 | 300 | ~$3.50 | ~10 min |
| Incremental (100 new) | 100 + 120 ctx | 11 | ~$0.15 | ~30 sec |
| Incremental (500 new) | 500 + 120 ctx | 31 | ~$0.50 | ~2 min |
| Incremental (0 new) | 0 | 0 | $0 | instant |

**ROI:** For daily/weekly updates, incremental saves ~95% of costs.
