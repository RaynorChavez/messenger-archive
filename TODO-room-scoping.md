# Room-Scoped Discussions & Topics

## Overview

Make discussions, topics, and analysis **per-room** so each group chat has independent analysis.

## Current State (Before)

- Analysis runs globally across ALL messages from ALL rooms
- Topics are global (shared across rooms)
- Discussions infer room from messages but aren't directly scoped
- 2 rooms: "General Chat" (183 discussions) and "Immersion" (0 discussions)

## Goal (After)

- Analyzing "General Chat" only processes messages from that room
- Topics are unique per room (e.g., "Philosophy" in General Chat vs "Philosophy" in Immersion)
- Each room has independent analysis history
- `room_id` is **required** on all analysis/classification endpoints

---

## Schema Changes

### Delete Existing Data (Starting Fresh)

```sql
DELETE FROM discussion_topics;
DELETE FROM discussion_messages;
DELETE FROM discussions;
DELETE FROM topics;
DELETE FROM discussion_analysis_runs;
DELETE FROM topic_classification_runs;
```

### Add room_id Columns

```sql
ALTER TABLE discussion_analysis_runs 
ADD COLUMN room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE;

ALTER TABLE discussions 
ADD COLUMN room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE;

ALTER TABLE topics 
ADD COLUMN room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE;

ALTER TABLE topic_classification_runs 
ADD COLUMN room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE;
```

### Update Topics Unique Constraint

```sql
ALTER TABLE topics DROP CONSTRAINT topics_name_key;
ALTER TABLE topics ADD CONSTRAINT topics_name_room_unique UNIQUE (name, room_id);
```

---

## Backend Changes

### `api/src/db.py` - Model Updates

Add `room_id` column + relationship to:
- `DiscussionAnalysisRun`
- `Discussion`
- `Topic`
- `TopicClassificationRun`

### `api/src/services/discussions.py` - Analyzer Updates

| Location | Method | Change |
|----------|--------|--------|
| Constructor | `__init__()` | Accept `room_id` parameter, store as `self.room_id` |
| Line ~590 | `analyze_all_messages()` | Add `.filter(Message.room_id == self.room_id)` |
| Line ~687 | `_load_incremental_context()` | Add room filter to context messages query |
| Line ~703 | `_load_incremental_context()` | Add `.filter(Discussion.room_id == self.room_id)` |
| Line ~826 | `analyze_incremental()` | Add `.filter(Message.room_id == self.room_id)` |
| `_store_discussion()` | Store discussion | Set `room_id=self.room_id` on new discussions |
| Topic classifier | Classification | Filter by room, create room-scoped topics |

### `api/src/routers/discussions.py` - Endpoint Updates

| Endpoint | Change |
|----------|--------|
| `POST /analyze` | Add `room_id: int` required query param |
| `GET /analyze/preview` | Add `room_id: int` required query param |
| `GET /analysis-status` | Add `room_id: int` required query param |
| `POST /classify-topics` | Add `room_id: int` required query param |
| `GET /classify-topics/status` | Add `room_id: int` required query param |
| `GET /topics/list` | Make `room_id: int` required |

---

## Frontend Changes

### `web/src/lib/api.ts` - API Function Updates

```typescript
// All these get room_id as required first parameter:
analyze: (roomId: number, mode?: "incremental" | "full") => ...
analysisPreview: (roomId: number) => ...
analysisStatus: (roomId: number) => ...
classifyTopics: (roomId: number) => ...
topicClassificationStatus: (roomId: number) => ...
listTopics: (roomId: number) => ...
```

### `web/src/app/discussions/page.tsx` - Page Updates

- Pass `currentRoom.id` to all analysis/classification API calls
- Disable analyze/classify buttons if no room selected
- Update polling to include room_id

---

## Implementation Order

1. ✅ Write migration SQL
2. ⬜ Update `api/src/db.py` - Add room_id to models
3. ⬜ Update `api/src/services/discussions.py` - Add room filtering
4. ⬜ Update `api/src/routers/discussions.py` - Add room_id params
5. ⬜ Update `web/src/lib/api.ts` - Update function signatures
6. ⬜ Update `web/src/app/discussions/page.tsx` - Pass room_id
7. ⬜ Run migration locally
8. ⬜ Test locally
9. ⬜ Deploy to production
10. ⬜ Run migration on production

---

## Files to Modify

| File | Changes |
|------|---------|
| `api/src/db.py` | Add room_id to 4 models |
| `api/src/services/discussions.py` | Add room filtering to analyzer |
| `api/src/routers/discussions.py` | Add room_id param to 6 endpoints |
| `web/src/lib/api.ts` | Update 6 function signatures |
| `web/src/app/discussions/page.tsx` | Pass room_id to all calls |

---

## Migration Script

Save as `scripts/migrate-room-scoping.sql`:

```sql
-- Room-scoping migration for discussions & topics
-- This deletes all existing analysis data and adds room_id columns

-- Step 1: Delete existing data (starting fresh per-room)
DELETE FROM discussion_topics;
DELETE FROM discussion_messages;
DELETE FROM discussions;
DELETE FROM topics;
DELETE FROM discussion_analysis_runs;
DELETE FROM topic_classification_runs;

-- Step 2: Add room_id columns
ALTER TABLE discussion_analysis_runs 
ADD COLUMN room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE;

ALTER TABLE discussions 
ADD COLUMN room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE;

ALTER TABLE topics 
ADD COLUMN room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE;

ALTER TABLE topic_classification_runs 
ADD COLUMN room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE;

-- Step 3: Update topics unique constraint (name unique per room, not globally)
ALTER TABLE topics DROP CONSTRAINT topics_name_key;
ALTER TABLE topics ADD CONSTRAINT topics_name_room_unique UNIQUE (name, room_id);
```

Run with:
```bash
# Local
docker exec -i archive-postgres psql -U archive -d messenger_archive < scripts/migrate-room-scoping.sql

# Production
ssh ubuntu@98.86.15.121 "docker exec -i archive-postgres psql -U archive -d messenger_archive" < scripts/migrate-room-scoping.sql
```
