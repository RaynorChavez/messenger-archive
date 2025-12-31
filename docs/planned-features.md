# Planned Features

## 1. Semantic Search Service ✅ DONE

Full-text semantic search across the archive using vector embeddings.

### Implementation Summary

- **Database:** `pgvector/pgvector:pg15` image with `embeddings` table, HNSW index
- **Embedding Service:** `api/src/services/embeddings.py` using Gemini `text-embedding-004` (768 dimensions)
- **Search API:** `GET /api/search?q=<query>&scope=<scope>&page=1&page_size=20` with hybrid scoring (0.5 semantic + 0.5 keyword)
- **Reindex API:** `POST /api/search/reindex` with progress tracking
- **Frontend:** Semantic search page with scope tabs, result cards, score bars
- **Real-time:** New messages embedded automatically via archive-service

### Additional Features (Dec 31, 2024)
- **Search in navbar** - Added to sidebar navigation
- **Pagination** - Full pagination support with page/page_size params
- **Collapsible sections** - Result sections collapse/expand, first with results expanded by default
- **Discussions page search** - Search bar with search-as-you-type (debounced via `useDeferredValue`)
- **Participant-based search** - Searching a person's name finds discussions they participated in:
  - Keyword scoring includes participant names (0.8 score)
  - Semantic search finds people, then maps to their discussions (0.85 factor for indirect match)

### Files Changed
- `docker-compose.yml` - pgvector image
- `scripts/init-db.sql` - embeddings table
- `scripts/migrate-pgvector.sql` - migration for existing DBs
- `api/requirements.txt` - pgvector package
- `api/src/db.py` - Embedding model
- `api/src/services/embeddings.py` - EmbeddingService
- `api/src/routers/search.py` - Search endpoints with pagination + participant search
- `api/src/main.py` - Init embedding service
- `web/src/lib/api.ts` - Search types and methods
- `web/src/app/search/page.tsx` - Semantic search UI with collapsible sections
- `web/src/app/settings/page.tsx` - Reindex button
- `web/src/app/discussions/page.tsx` - Search bar with search-as-you-type
- `web/src/components/layout/sidebar.tsx` - Search link in navigation
- `archive-service/src/main.py` - Embed on message store

### First-Time Setup
```bash
# Backup and migrate
docker compose exec postgres pg_dump -U archive -d messenger_archive > backup.sql
docker compose down
docker compose up -d postgres
docker compose exec postgres psql -U archive -d messenger_archive -f /docker-entrypoint-initdb.d/migrate-pgvector.sql
docker compose up -d

# Build index via Settings page or API
curl -X POST http://localhost:8000/api/search/reindex
```

---

## 2. Virtual Chat

AI-powered group chat where Gemini agents roleplay as archived people based on their documented messages and chat style.

### Components

#### 2.1 Database Schema
```sql
CREATE TABLE virtual_conversations (
  id SERIAL PRIMARY KEY,
  title VARCHAR(255),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE virtual_participants (
  id SERIAL PRIMARY KEY,
  conversation_id INTEGER REFERENCES virtual_conversations(id) ON DELETE CASCADE,
  person_id INTEGER REFERENCES people(id),
  joined_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(conversation_id, person_id)
);

CREATE TABLE virtual_messages (
  id SERIAL PRIMARY KEY,
  conversation_id INTEGER REFERENCES virtual_conversations(id) ON DELETE CASCADE,
  sender_type VARCHAR(20) NOT NULL,  -- 'user' or 'agent'
  person_id INTEGER REFERENCES people(id),  -- NULL for user, set for agent
  content TEXT NOT NULL,
  mentions INTEGER[],  -- Array of person_ids mentioned
  created_at TIMESTAMP DEFAULT NOW()
);
```

#### 2.2 Agent Service
Each person gets a Gemini agent with:
- **System prompt** built from:
  - Their profile summary
  - Sample messages showing their writing style
  - Topics they frequently discuss
  - Their reply patterns (how they respond to others)
- **Persona traits** extracted from their messages:
  - Formality level
  - Emoji usage
  - Typical message length
  - Language preferences (English, Tagalog, mixed)

#### 2.3 Prompt Caching
Use Gemini's context caching API to cache persona context:
```python
# Cache the persona (valid for 1 hour by default)
cached_content = client.caching.create(
  model="gemini-2.0-flash",
  contents=[persona_system_prompt, sample_messages],
  ttl="3600s"
)

# Use cached context for responses
response = client.models.generate_content(
  model="gemini-2.0-flash",
  contents=[cached_content, conversation_history, new_message]
)
```

#### 2.4 @Mention & Reply Logic
- Parse `@Name` mentions in user messages
- For each mentioned person:
  1. Agent evaluates if they would naturally respond
  2. Consider: topic relevance, their activity patterns, relationship with other participants
  3. If responding, generate reply in their style
- Unmentioned agents can also chime in if topic is relevant to them

#### 2.5 Frontend
- `/virtual-chat` page
- Conversation list sidebar
- Create new conversation (select participants)
- Chat interface:
  - User input with @mention autocomplete
  - Agent responses with avatar and name
  - Typing indicators while agents "think"
  - Load previous conversations

---

## 3. Enhanced Profile Summaries

Improve profile summaries by including discussion context and reply chains.

### Current State
- Summaries are generated from raw messages only
- No context about what discussion the message was part of
- No context about what they were replying to

### Enhancements

#### 3.1 Include Discussion Context
When fetching messages for summary generation:
```python
messages_with_context = db.query(
  Message, Discussion.title, Discussion.summary
).outerjoin(
  DiscussionMessage, Message.id == DiscussionMessage.message_id
).outerjoin(
  Discussion, DiscussionMessage.discussion_id == Discussion.id
).filter(Message.sender_id == person_id)
```

Format for prompt:
```
[2025-12-30 in "Buddhist Philosophy vs Clinical Psychology"]
User: "It is the western trend to experience the bliss of Buddhist meditation..."
```

#### 3.2 Include Reply Context
When a message is a reply, include what they were responding to:
```
[2025-12-30 in "Logic and Mathematics"]
> Original by John: "me talking to my bs math graduate gf about logic"
User replied: "reasonable crashout tbh"
```

#### 3.3 Updated Summary Prompt
```
Analyze this person's messages to create a profile summary.

Each message includes:
- The discussion topic it was part of (if detected)
- What message they were replying to (if applicable)

Use this context to understand:
- What topics they engage with most
- How they respond to different people
- Their role in discussions (initiator, responder, mediator, etc.)
- Their communication style in different contexts
```

---

## 4. Profile Activity Charts

Activity/frequency visualization on each person's profile page showing their messaging patterns over time.

### Components

#### 4.1 API Endpoint
```
GET /api/people/{id}/activity?period=<period>&granularity=<granularity>

period: all | year | 6months | 3months | month
granularity: day | week | month
```

Response:
```json
{
  "person_id": 123,
  "period": "6months",
  "granularity": "week",
  "data": [
    {"date": "2025-01-06", "count": 45},
    {"date": "2025-01-13", "count": 32},
    ...
  ],
  "total_messages": 1234,
  "most_active_day": "Monday",
  "most_active_hour": 14
}
```

#### 4.2 SQL Query
```sql
SELECT 
  DATE_TRUNC('week', timestamp) as period,
  COUNT(*) as count
FROM messages
WHERE sender_id = :person_id
  AND timestamp >= NOW() - INTERVAL '6 months'
GROUP BY DATE_TRUNC('week', timestamp)
ORDER BY period;
```

#### 4.3 Frontend Component
- Line chart or bar chart (using recharts or similar)
- Period selector (all time, 1 year, 6 months, etc.)
- Granularity toggle (daily, weekly, monthly)
- Additional stats:
  - Most active day of week
  - Most active time of day
  - Average messages per day/week

#### 4.4 Profile Page Integration
Add chart section to `/people/[id]` page below the summary:
```
+----------------------------------+
| Profile Header + Summary         |
+----------------------------------+
| Activity Chart                   |
| [Period: 6 months v] [Weekly v]  |
| ████ ██ ████████ ███ █████      |
+----------------------------------+
| Most active: Monday @ 2pm        |
| Avg: 12 messages/day             |
+----------------------------------+
| Recent Messages                  |
+----------------------------------+
```

---

---

## 5. Dashboard Recent Activity Avatars

Show profile pictures/avatars in the recent activity feed on the dashboard.

### Current State
- Recent activity shows messages with sender name only
- No visual avatar/profile picture

### Changes

#### 5.1 API
The `/api/stats/recent` endpoint already returns `sender.avatar_url` - just need to use it in the frontend.

#### 5.2 Frontend
Update dashboard recent activity component:
```tsx
<div className="flex items-start gap-3">
  <Avatar>
    <AvatarImage src={message.sender?.avatar_url} />
    <AvatarFallback>{message.sender?.display_name?.[0]}</AvatarFallback>
  </Avatar>
  <div>
    <span className="font-medium">{message.sender?.display_name}</span>
    <p className="text-muted-foreground">{message.content}</p>
  </div>
</div>
```

#### 5.3 Avatar URL Handling
Matrix avatar URLs are in `mxc://` format. Need to convert to HTTP:
```typescript
function mxcToHttp(mxcUrl: string): string {
  if (!mxcUrl?.startsWith('mxc://')) return mxcUrl;
  const [serverName, mediaId] = mxcUrl.replace('mxc://', '').split('/');
  return `${MATRIX_HOMESERVER}/_matrix/media/v3/thumbnail/${serverName}/${mediaId}?width=40&height=40`;
}
```

---

## 6. Incremental Discussion Analysis

Cost-efficient analysis mode that only processes new messages since the last run, with context overlap for continuity.

### Problem

Full analysis costs ~$3.50 for ~6,000 messages due to multi-turn function calling (~7 API calls per window). As message history grows, this becomes unsustainable.

### Solution

**Incremental mode** that:
1. Only analyzes new messages since last completed run
2. Includes 4 windows (~120 messages) of overlap for context
3. Append-only - can extend existing discussions but cannot delete/remove

### Database Changes

```sql
ALTER TABLE discussion_analysis_runs ADD COLUMN 
  start_message_id INTEGER,           -- First new message analyzed
  end_message_id INTEGER,             -- Last message analyzed  
  context_start_message_id INTEGER,   -- Start of context window (4 windows back)
  mode VARCHAR(20) DEFAULT 'full';    -- 'full' or 'incremental'
```

### Analysis Modes

#### Full Mode (first run or manual reset)
- Clears all existing discussions
- Analyzes all messages from scratch
- Use case: First run, or when data is corrupted/inconsistent

#### Incremental Mode (default)
- Finds last completed run's `end_message_id`
- Loads 4 windows of context (read-only)
- Analyzes new messages only
- **Can:** Extend existing discussions, create new discussions
- **Cannot:** Delete discussions, remove messages from discussions, modify titles/summaries

### API Changes

```python
# POST /api/discussions/analyze
{
  "mode": "incremental" | "full",  # default: "incremental"
}

# GET /api/discussions/analysis-status
{
  ...existing fields...,
  "mode": "incremental",
  "context_messages": 120,
  "new_messages_analyzed": 500,
}
```

### Frontend Changes

- "Analyze" button defaults to incremental
- Show badge: "Incremental (523 new messages)"
- Dropdown/secondary button for "Full Re-analysis" with confirmation
- Status: "Analyzing 523 new messages (with 120 context)..."

### Cost Savings

| Scenario | Messages | Est. Cost |
|----------|----------|-----------|
| Full (6,000 msgs) | 6,000 | ~$3.50 |
| Incremental (100 new) | 100 + 120 context | ~$0.15 |
| Incremental (500 new) | 500 + 120 context | ~$0.50 |

**95%+ cost reduction** for routine updates.

### Edge Cases

1. **Discussion spans old and new:** Context windows let AI see continuation, adds to existing discussion
2. **Long gap between runs:** Still works, just takes longer
3. **First run ever:** Auto-falls back to full mode
4. **Previous run failed:** Uses last *completed* run for cutoff

---

## 7. Bug Fixes

### 7.1 Discussion `ended_at` Uses Current Time Instead of Message Timestamp ✅ FIXED

**Priority:** High

**Problem:**
When discussions are created, `started_at` and `ended_at` default to `datetime.now()`. The code attempts to update these based on message timestamps, but `ended_at` is incorrectly showing the analysis run date (Dec 30) for all discussions instead of the actual latest message date.

**Root cause:** When `ended_at` defaults to `datetime.now()` (today's date), the comparison `msg.timestamp > disc.ended_at` is always false for historical messages, so `ended_at` never gets updated.

**Fix applied:** Changed default `ended_at` to `datetime.min` (with timezone) so any message timestamp will be greater and trigger the update. Location: `api/src/services/discussions.py:344`

**Note:** Existing discussions need re-analysis to fix their `ended_at` values.

### 7.2 Profile Activity Chart Default Granularity ✅ FIXED

**Priority:** Low

**Problem:** Activity chart defaults to "weekly" granularity, which shows only 3 data points for recent data.

**Fix applied:** Changed default from `"week"` to `"day"` in `web/src/app/people/[id]/page.tsx:34`

### 7.3 Discussion Analysis Assigns Unrelated Messages with High Confidence

**Priority:** High

**Problem:** Messages about completely unrelated topics (e.g., 3-body problem, Kant's categories) are being assigned to discussions they don't belong to (e.g., "Underrated Bangsamoro Food") with 100% confidence. Investigation showed:
- 240 messages (~8 windows) between the original Bangsamoro message and the 3BP messages
- The discussion was kept "active" indefinitely
- AI assigned new messages to any active discussion without checking topic relevance

**Root Causes:**
1. Prompt lacks clear guidance on topic relevance for assignments
2. No mechanism to make discussions "dormant" after inactivity
3. Active discussions list only shows title + count, not topic context
4. No validation/sanity check on assignments

**Fixes:**

#### Fix 1: Improve Prompt with Clearer Rules

Update `PROMPT_TEMPLATE` in `api/src/services/discussions.py`:

```
RULES:
- Only assign a message to a discussion if it's ACTUALLY ABOUT that topic
- If a message doesn't fit any active discussion, either create a NEW one or leave assignments empty
- Confidence should be LOW (0.3-0.5) for tangentially related messages, HIGH (0.8-1.0) only for directly on-topic
- Do NOT assign messages to a discussion just because it's active - topic relevance is required
- A discussion can span multiple days - don't end it just because of time gaps
- End a discussion only when the topic has clearly concluded or shifted permanently
```

#### Fix 2: Auto-Dormancy After Inactivity

Track `last_active_window` for each discussion in `ActiveDiscussion` state:
- After **5 windows** (~100 messages) with no new assignments, mark as "dormant"
- Dormant discussions are removed from ACTIVE DISCUSSIONS list shown to AI
- Dormant discussions can be "revived" if a future message clearly relates (via inspect tool)
- This allows long-running discussions to span days while preventing "zombie" discussions

Changes needed:
```python
@dataclass
class ActiveDiscussion:
    ...
    last_active_window: int = 0  # Track which window last had activity
    dormant: bool = False        # Soft-ended, can be revived
```

#### Fix 3: Include Topic Keywords in Active Discussions

When creating a new discussion, generate lightweight topic keywords (separate from full summary which is generated at the end).

Change active discussions format from:
```json
{"id": 56, "title": "Underrated Bangsamoro Food", "message_count": 5}
```

To:
```json
{
  "id": 56, 
  "title": "Underrated Bangsamoro Food", 
  "topic_keywords": ["Filipino food", "Tawi-Tawi", "cuisine", "healthy eating"],
  "recent_participants": ["Roi Salamat"],
  "windows_since_active": 0
}
```

Generate keywords via quick AI call when discussion is created:
```python
async def _generate_topic_keywords(self, title: str, first_messages: List[str]) -> List[str]:
    """Generate 3-5 topic keywords for a new discussion."""
    prompt = f"Generate 3-5 topic keywords for a discussion titled '{title}' with messages: {first_messages[:3]}"
    # Quick lightweight call, no thinking budget needed
    ...
```

#### Fix 4: Post-Classification Validation (Logging)

After each window's classification, log suspicious assignments for review:
- Flag: message assigned to discussion inactive for 3+ windows with confidence >= 0.9
- Flag: message assigned to discussion where no other messages in current window are assigned
- Log warning with message content and discussion title for human review

```python
def _validate_classifications(self, classifications: List, current_window: int):
    """Log suspicious classifications for review."""
    for cls in classifications:
        for assignment in cls.assignments:
            disc = self.state.active_discussions.get(assignment.discussion_id)
            if disc:
                windows_inactive = current_window - disc.last_active_window
                if windows_inactive >= 3 and assignment.confidence >= 0.9:
                    logger.warning(
                        f"Suspicious assignment: msg {cls.message_id} -> discussion '{disc.title}' "
                        f"(inactive {windows_inactive} windows) with confidence {assignment.confidence}"
                    )
```

---

## 8. Discussion Page Enhancements ✅ DONE

### 8.1 Virtualized Infinite Scroll ✅
- Implemented `@tanstack/react-virtual` for efficient rendering
- Only renders visible discussion cards
- Loads more as user scrolls (50 per page)

### 8.2 Timeline API Endpoint ✅
- `GET /api/discussions/timeline` returns date counts for full timeline
- Timeline loads all dates upfront, discussions load paginated
- Supports topic_id filter

### 8.3 Date Filtering ✅
- `GET /api/discussions?date=YYYY-MM-DD` filters by date
- Clicking timeline bead fetches discussions for that date
- Works with topic filter

### 8.4 Discussion Context Expansion ✅
- "Show earlier messages" / "Show later messages" buttons
- `GET /api/discussions/{id}/context?position=before|after&limit=5`
- Shows messages before/after discussion with visual separator

### 8.5 In-Thread Gap Expansion ✅
- Detects gaps between discussion messages where other messages occurred
- "Show N hidden messages" buttons between messages
- `GET /api/discussions/{id}/gaps` returns gap info
- `GET /api/discussions/{id}/gap-messages` returns messages in a gap
- Similar to GitHub PR diff "show more context" feature

---

## Implementation Order

Recommended sequence:

1. **Bug Fix: Discussion dates** ✅ DONE
   - Fixed `ended_at` to use actual message timestamps

2. **Incremental Discussion Analysis** (cost savings - high priority)
   - Essential for sustainable ongoing analysis
   - Should implement before running more full analyses

3. **Semantic Search** ✅ DONE
   - Hybrid search (semantic + keyword) with 0.5 alpha
   - Embeddings for messages, discussions, people, topics
   - Real-time embedding for new messages
   - Search in navbar + discussions page search-as-you-type
   - Participant-based discussion search
   - Collapsible result sections, pagination support

4. **Enhanced Profile Summaries** (quick win)
   - Relatively small change to existing code
   - Improves data quality for Virtual Chat personas

5. **Profile Activity Charts** ✅ DONE
   - Simple SQL aggregation + chart component
   - Nice visual addition to profile pages

6. **Dashboard Avatars** ✅ DONE
   - Added avatars to recent activity feed
   - mxc:// to HTTP URL conversion

7. **Database Page Tables** ✅ DONE
   - Added discussions, discussion_messages, topics, discussion_topics tables

8. **Bug Fix: Discussion Classification** ✅ DONE
   - Improved prompt with clearer topic relevance rules
   - Auto-dormancy after 5 windows of inactivity
   - Topic keywords generated when creating discussions
   - Validation logging for suspicious assignments

9. **Discussion Page Enhancements** ✅ DONE
   - Virtualized infinite scroll
   - Full timeline from API
   - Date filtering
   - Context expansion (before/after)
   - In-thread gap expansion

10. **Virtual Chat** (capstone)
    - Depends on good profile summaries
    - Can use semantic search to find relevant messages for context
