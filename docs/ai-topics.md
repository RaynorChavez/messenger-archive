# Topics as Discussion Filters - Implementation Plan

## Summary
- Horizontal topic filter bar on Discussions page with colored pills
- AI-generated topics with descriptions, can see existing topics on re-run
- Discussions can belong to multiple topics (1-3 typically)
- Background classification with its own progress bar
- Topic pills on discussion cards with hover tooltips for descriptions
- Two separate buttons: [Analyze Messages] [Classify Topics]
- Always send response_schema to Gemini for structured JSON output

## Database Tables

```sql
CREATE TABLE topics (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    color VARCHAR(7) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE discussion_topics (
    discussion_id INTEGER REFERENCES discussions(id) ON DELETE CASCADE,
    topic_id INTEGER REFERENCES topics(id) ON DELETE CASCADE,
    PRIMARY KEY (discussion_id, topic_id)
);

CREATE TABLE topic_classification_runs (
    id SERIAL PRIMARY KEY,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) DEFAULT 'running',
    topics_created INTEGER DEFAULT 0,
    discussions_classified INTEGER DEFAULT 0,
    error_message TEXT
);
```

## Color Palette

```typescript
const TOPIC_COLORS = [
  '#6366f1', // Indigo
  '#f43f5e', // Rose
  '#f59e0b', // Amber
  '#10b981', // Emerald
  '#0ea5e9', // Sky
  '#8b5cf6', // Violet
  '#14b8a6', // Teal
  '#f97316', // Orange
  '#ec4899', // Pink
  '#06b6d4', // Cyan
];
```

## UI Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Discussions                          [Analyze Messages] [Classify Topics]│
├─────────────────────────────────────────────────────────────────────────┤
│ Analysis: [██████████████░░░░░░] 70%                                    │
│ Topics:   [████████░░░░░░░░░░░░] 40%    ← only shows when classifying   │
├─────────────────────────────────────────────────────────────────────────┤
│ [All] [●Philosophy] [●Ethics] [●Politics] [●Culture] ...       ← scroll │
│              ↑ tooltip on hover: "Core philosophical discussions..."    │
├─────────────┬───────────────────────────────────────────────────────────┤
│  Timeline   │  ┌─────────────────────────────────────────────────────┐  │
│  ● All      │  │ Hegel's Dialectics                                  │  │
│  ● Dec 30   │  │ 12 messages · 3 participants · 2h ago               │  │
│  ● Dec 29   │  │ [●Philosophy] [●Metaphysics]                        │  │
│  ● Dec 28   │  │ Summary preview text here...                        │  │
│             │  └─────────────────────────────────────────────────────┘  │
└─────────────┴───────────────────────────────────────────────────────────┘
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/topics` | List all topics with discussion counts |
| `POST` | `/api/discussions/classify-topics` | Start classification (background) |
| `GET` | `/api/discussions/classify-topics/status` | Get classification progress |
| `GET` | `/api/discussions?topic_id=X` | Filter discussions by topic |

## AI Prompt for Classification

```
You are classifying discussions from "Manila Dialectics Society", a Filipino philosophy discussion group. They discuss philosophy, politics, culture, history, and intellectual discourse.

EXISTING TOPICS (reuse if appropriate, modify descriptions, or create new ones):
{existing_topics as JSON: name, description}

DISCUSSIONS TO CLASSIFY:
{discussions as JSON: id, title, summary}

Create 5-10 topic categories that best organize this content. Each discussion should belong to 1-3 topics.

Guidelines:
- Reuse existing topic names when they fit
- Create new topics for themes not covered
- Topics should be broad enough to group multiple discussions
- Each topic needs a concise description (1 sentence)

Output JSON:
{
  "topics": [
    {"name": "Philosophy", "description": "Core philosophical discussions including metaphysics, epistemology, and major thinkers"}
  ],
  "assignments": [
    {"discussion_id": 1, "topic_names": ["Philosophy", "Ethics"]}
  ]
}
```

## Gemini Response Schema

```python
TOPIC_CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"}
                },
                "required": ["name", "description"]
            }
        },
        "assignments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "discussion_id": {"type": "integer"},
                    "topic_names": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["discussion_id", "topic_names"]
            }
        }
    },
    "required": ["topics", "assignments"]
}
```

## AI Classification Flow

1. User clicks "Classify Topics"
2. Create `TopicClassificationRun` record with status `running`
3. Start background thread
4. Fetch all discussions (id, title, summary) and existing topics
5. Call Gemini with prompt and response_schema
6. Parse response:
   - Create new topics (assign colors from palette)
   - Update existing topic descriptions if changed
   - Clear all `discussion_topics` entries
   - Insert new assignments
   - Delete orphaned topics (topics with no discussions)
7. Update run status to `completed`

## Implementation Order

1. Database tables (SQL) ✅
2. SQLAlchemy models (`db.py`)
3. Pydantic schemas (`schemas/discussion.py`)
4. Classification service (`services/discussions.py`)
5. API endpoints (`routers/discussions.py`)
6. Frontend API client (`api.ts`)
7. Update Discussions page UI
8. Remove Topics from sidebar
