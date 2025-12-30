# AI-Powered Discussion Detection

## Overview

Detect and group messages into thematic discussions using Gemini with function calling. Messages are processed in sliding windows, and the AI can inspect existing discussions before making assignments.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Discussion Analysis Flow                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. INITIALIZATION                                               │
│     ├── Fetch all messages ordered by timestamp                  │
│     ├── Calculate windows (100 msgs, 30% overlap)                │
│     └── Initialize active_discussions = {}                       │
│                                                                  │
│  2. FOR EACH WINDOW                                              │
│     ├── Build prompt with messages + active discussion list      │
│     ├── Provide tool: inspect_discussion(id)                     │
│     │   └── Returns: title + all messages in discussion          │
│     ├── AI classifies each message (JSON output)                 │
│     ├── Parse response, update active_discussions                │
│     ├── Mark ended discussions                                   │
│     └── Rate limit pause if needed                               │
│                                                                  │
│  3. POST-PROCESSING                                              │
│     ├── For each discussion: generate summary                    │
│     ├── Calculate stats (participants, time range)               │
│     └── Store to database                                        │
│                                                                  │
│  4. SAFEGUARDS                                                   │
│     ├── Max 500 messages per discussion                          │
│     ├── Token usage tracking                                     │
│     └── Graceful failure handling                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Sliding Window Approach

```
Messages:    [1] [2] [3] [4] [5] [6] [7] [8] [9] [10] [11] [12] ...
             |_______Window 1_______|
                         |_______Window 2_______|
                                     |_______Window 3_______|

Window size: 100 messages
Overlap: 30 messages (30%)
Net progress per window: 70 messages
```

The overlap ensures discussions spanning window boundaries are captured correctly.

## Function Calling

The AI has access to one tool:

### `inspect_discussion(discussion_id: int)`

Returns all messages in a discussion so the AI can determine if a new message belongs to it.

**Input:**
```json
{"discussion_id": 12}
```

**Output:**
```json
{
  "discussion_id": 12,
  "title": "Existentialism and Kierkegaard",
  "message_count": 42,
  "messages": [
    {"id": 4501, "sender": "Paulina", "content": "I think Kierkegaard's leap of faith..."},
    {"id": 4505, "sender": "Juan", "content": "The aesthetic vs ethical stages..."},
    ...
  ]
}
```

## LLM Output Format (JSON Mode)

For each window, the AI outputs structured JSON:

```json
{
  "classifications": [
    {
      "message_id": 4521,
      "assignments": [
        {"discussion_id": 12, "confidence": 0.95}
      ]
    },
    {
      "message_id": 4522,
      "assignments": [
        {"discussion_id": 12, "confidence": 0.88}
      ]
    },
    {
      "message_id": 4523,
      "assignments": [
        {"discussion_id": "NEW", "title": "Hegel's Dialectic Method", "confidence": 0.92}
      ]
    },
    {
      "message_id": 4524,
      "assignments": [
        {"discussion_id": 12, "confidence": 0.72},
        {"discussion_id": 15, "confidence": 0.65}
      ]
    },
    {
      "message_id": 4525,
      "assignments": []
    }
  ],
  "discussions_ended": [8, 11],
  "new_discussions": [
    {"temp_id": "NEW_1", "title": "Hegel's Dialectic Method"}
  ]
}
```

**Notes:**
- `assignments: []` means the message is skipped (noise, greetings, etc.)
- A message can have multiple assignments (bridges topics)
- `discussion_id: "NEW"` creates a new discussion with the given title
- `discussions_ended` lists discussions that concluded in this window

## Database Schema

```sql
-- Track analysis runs
CREATE TABLE discussion_analysis_runs (
    id SERIAL PRIMARY KEY,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    status TEXT DEFAULT 'running',  -- running, completed, failed
    windows_processed INTEGER DEFAULT 0,
    total_windows INTEGER,
    discussions_found INTEGER DEFAULT 0,
    tokens_used INTEGER DEFAULT 0,
    error_message TEXT
);

-- Detected discussions
CREATE TABLE discussions (
    id SERIAL PRIMARY KEY,
    analysis_run_id INTEGER REFERENCES discussion_analysis_runs(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    summary TEXT,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    ended_at TIMESTAMP WITH TIME ZONE NOT NULL,
    message_count INTEGER DEFAULT 0,
    participant_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Many-to-many: messages can belong to multiple discussions
CREATE TABLE discussion_messages (
    discussion_id INTEGER REFERENCES discussions(id) ON DELETE CASCADE,
    message_id INTEGER REFERENCES messages(id) ON DELETE CASCADE,
    confidence FLOAT DEFAULT 1.0,
    PRIMARY KEY (discussion_id, message_id)
);

-- Indexes
CREATE INDEX idx_discussion_messages_message ON discussion_messages(message_id);
CREATE INDEX idx_discussion_messages_discussion ON discussion_messages(discussion_id);
CREATE INDEX idx_discussions_analysis_run ON discussions(analysis_run_id);
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/discussions/analyze` | Start new analysis run (replaces previous) |
| `GET` | `/api/discussions/analysis-status` | Get current/latest run status |
| `GET` | `/api/discussions` | List all discussions (paginated) |
| `GET` | `/api/discussions/:id` | Get discussion with messages and summary |

## Pydantic Schemas

### Request/Response Validation

```python
class DiscussionAssignment(BaseModel):
    discussion_id: int | Literal["NEW"]
    title: Optional[str] = None  # Required if discussion_id == "NEW"
    confidence: float = Field(ge=0.0, le=1.0)

class MessageClassification(BaseModel):
    message_id: int
    assignments: List[DiscussionAssignment]

class NewDiscussion(BaseModel):
    temp_id: str
    title: str

class WindowClassificationResponse(BaseModel):
    classifications: List[MessageClassification]
    discussions_ended: List[int] = []
    new_discussions: List[NewDiscussion] = []
```

### API Response Schemas

```python
class DiscussionBrief(BaseModel):
    id: int
    title: str
    summary: Optional[str]
    started_at: datetime
    ended_at: datetime
    message_count: int
    participant_count: int

class DiscussionMessage(BaseModel):
    id: int
    content: str
    timestamp: datetime
    sender: PersonBrief
    confidence: float

class DiscussionFull(BaseModel):
    id: int
    title: str
    summary: Optional[str]
    started_at: datetime
    ended_at: datetime
    message_count: int
    participant_count: int
    messages: List[DiscussionMessage]

class AnalysisStatus(BaseModel):
    status: str  # running, completed, failed, none
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    windows_processed: int
    total_windows: int
    discussions_found: int
    tokens_used: int
    error_message: Optional[str]
```

## Prompt Template

```
You are analyzing messages from a philosophy discussion group called "Manila Dialectics Society" to identify distinct discussion threads.

## Your Task
Classify each message into one or more thematic discussions. Messages that are just greetings, reactions, or off-topic noise should have empty assignments.

## Active Discussions
{JSON list of active discussions with id and title, or "None yet" for first window}

## Tools Available
- inspect_discussion(discussion_id): View all messages in a discussion to understand its context

## Messages to Classify
{JSON array of messages with id, timestamp, sender, content}

## Instructions
1. For each message, determine which discussion(s) it belongs to
2. Use inspect_discussion(id) if you need to see a discussion's content before deciding
3. Create new discussions when distinct topics emerge
4. A message can belong to multiple discussions if it bridges topics
5. Assign confidence scores (0.0-1.0) based on how clearly the message fits
6. Mark discussions as ended if they naturally conclude in this window

## Response Format
Respond with valid JSON matching this schema:
{
  "classifications": [
    {"message_id": int, "assignments": [{"discussion_id": int|"NEW", "title": str|null, "confidence": float}]}
  ],
  "discussions_ended": [int],
  "new_discussions": [{"temp_id": str, "title": str}]
}
```

## File Changes Required

| File | Action |
|------|--------|
| `api/src/db.py` | Add `DiscussionAnalysisRun`, `Discussion`, `DiscussionMessage` models |
| `api/src/services/discussions.py` | **New** - `DiscussionAnalyzer` class |
| `api/src/routers/discussions.py` | **New** - Discussion endpoints |
| `api/src/schemas/discussion.py` | **New** - Pydantic schemas |
| `api/src/main.py` | Register discussions router |
| `web/src/lib/api.ts` | Add discussion API methods |
| `web/src/app/discussions/page.tsx` | **New** - Discussions list page |
| `web/src/app/discussions/[id]/page.tsx` | **New** - Discussion detail page |
| `web/src/components/layout/sidebar.tsx` | Add Discussions nav with AI icon |

## UI Design

### Discussions List Page (`/discussions`)

```
┌─────────────────────────────────────────────────────────────────┐
│ Discussions ✨                              [Analyze] button    │
├─────────────────────────────────────────────────────────────────┤
│ Last analyzed: 2 hours ago · 57 discussions found               │
│ [Progress bar if analysis running]                              │
├─────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Existentialism and Kierkegaard                              │ │
│ │ Dec 16-18 · 42 messages · 8 participants                    │ │
│ │ "A deep dive into Fear and Trembling and the concept of..." │ │
│ └─────────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Philippine Economic Policy                                  │ │
│ │ Dec 17-19 · 28 messages · 5 participants                    │ │
│ │ "Discussion analyzing inflation rates and monetary..."      │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Discussion Detail Page (`/discussions/:id`)

```
┌─────────────────────────────────────────────────────────────────┐
│ ← Back to Discussions                                           │
├─────────────────────────────────────────────────────────────────┤
│ Existentialism and Kierkegaard                                  │
│ Dec 16, 2025 - Dec 18, 2025 · 42 messages · 8 participants      │
├─────────────────────────────────────────────────────────────────┤
│ Summary                                                         │
│ This discussion explored Kierkegaard's concept of the leap of   │
│ faith, comparing it to Nietzsche's proclamation of the death    │
│ of God. Participants debated the relationship between...        │
├─────────────────────────────────────────────────────────────────┤
│ Messages                                          [scrollable]  │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Paulina · Dec 16, 11:42 PM                  confidence: 95% │ │
│ │ I think Kierkegaard's leap of faith is misunderstood        │ │
│ ├─────────────────────────────────────────────────────────────┤ │
│ │ Juan · Dec 16, 11:45 PM                     confidence: 92% │ │
│ │ The aesthetic vs ethical stages are fascinating             │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Token Usage Estimates

| Component | Tokens (estimate) |
|-----------|-------------------|
| Per window input | ~3,000 |
| Per window output | ~500 |
| Per inspection call | ~1,000 |
| Total for 82 windows | ~300k-500k |
| Summary generation | ~50k |
| **Total** | **~400k-600k** |

Well within rate limits when processed over time with pauses.

## Safeguards

1. **Max messages per discussion:** 500 (prevents mega-discussions)
2. **Rate limiting:** Respect 800k tokens/min limit
3. **Progress tracking:** Can resume if interrupted
4. **Validation:** All AI output validated against Pydantic schemas
5. **Error handling:** Failed windows logged, analysis can continue
6. **Replace mode:** New analysis replaces previous (no duplicates)

## Configuration

| Setting | Value | Notes |
|---------|-------|-------|
| Window size | 100 messages | Balance between context and token usage |
| Overlap | 30% (30 messages) | Catch cross-boundary discussions |
| Max messages per discussion | 500 | Prevent runaway grouping |
| Model | gemini-2.0-flash | Function calling support |
| Thinking budget | 712 tokens | For complex classification |
| Max output tokens | 4096 | Room for full JSON response |
