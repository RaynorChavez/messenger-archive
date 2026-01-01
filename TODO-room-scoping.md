# TODO: Room-Scoped Discussions & Topics

## Problem

Currently, discussions analysis and topics are **global** - they span all rooms (group chats). This doesn't make sense because:
- Different GCs have different conversations
- Topics in "General Chat" may be different from "Immersion"
- Analysis should be per-room so you can analyze one GC without affecting others

## Current State

### What's scoped by room (working):
- ✅ Messages list - filtered by room_id
- ✅ Discussions list - accepts room_id parameter, filters by messages in that room
- ✅ Timeline - accepts room_id parameter

### What's NOT scoped by room (needs fix):
- ❌ **Analysis runs** - runs on ALL messages globally
- ❌ **Discussions** - don't have a room_id, inferred from messages
- ❌ **Topics** - global, not per-room
- ❌ **Topic classification** - runs globally

## Schema Changes Needed

### 1. `discussion_analysis_runs` table
Add `room_id` column:
```sql
ALTER TABLE discussion_analysis_runs ADD COLUMN room_id INTEGER REFERENCES rooms(id);
```

### 2. `discussions` table
Add `room_id` column:
```sql
ALTER TABLE discussions ADD COLUMN room_id INTEGER REFERENCES rooms(id);
```

### 3. `topics` table
Add `room_id` column (topics become per-room):
```sql
ALTER TABLE topics ADD COLUMN room_id INTEGER REFERENCES rooms(id);
-- Drop unique constraint on name, add unique on (name, room_id)
ALTER TABLE topics DROP CONSTRAINT topics_name_key;
ALTER TABLE topics ADD CONSTRAINT topics_name_room_unique UNIQUE (name, room_id);
```

### 4. `topic_classification_runs` table
Add `room_id` column:
```sql
ALTER TABLE topic_classification_runs ADD COLUMN room_id INTEGER REFERENCES rooms(id);
```

## API Changes Needed

### `/discussions/analyze` endpoint
- Add `room_id` required parameter
- Filter messages by room when analyzing
- Store room_id in the analysis run

### `/discussions/classify-topics` endpoint
- Add `room_id` required parameter
- Only classify discussions for that room
- Create topics scoped to that room

### `/discussions/topics/list` endpoint
- Already updated to accept `room_id` parameter (partial fix done)
- Should require room_id once topics are per-room

### `/discussions/analysis-status` endpoint
- Add `room_id` parameter to get status for specific room

### `/discussions/analyze/preview` endpoint
- Add `room_id` parameter

## Frontend Changes Needed

### `web/src/app/discussions/page.tsx`
- Pass `currentRoom.id` to analyze endpoint
- Pass `currentRoom.id` to classify-topics endpoint
- Update status polling to be room-specific
- Already passes room_id to list/timeline (done)

### `web/src/lib/api.ts`
- Update `analyze()` to accept room_id
- Update `classifyTopics()` to accept room_id
- Update `analysisStatus()` to accept room_id
- Update `analysisPreview()` to accept room_id
- `listTopics()` already updated (done)

## Migration Strategy

1. Add nullable room_id columns to all tables
2. Backfill existing data:
   - For discussions: infer room_id from the first message in the discussion
   - For topics: duplicate topics for each room that has discussions with that topic
   - For analysis runs: set to NULL (legacy global runs)
3. Make room_id NOT NULL for new rows
4. Update all API endpoints
5. Update frontend

## Files to Modify

### Backend
- `api/src/db.py` - Add room_id columns to models
- `api/src/routers/discussions.py` - Update all endpoints
- `api/src/services/discussions.py` - Update DiscussionAnalyzer to be room-aware

### Frontend
- `web/src/app/discussions/page.tsx` - Pass room_id to all operations
- `web/src/lib/api.ts` - Update API function signatures

## Partial Fix Applied (2026-01-02)

The following partial fix was applied but is incomplete:
- `listTopics()` API now accepts `room_id` parameter
- Frontend passes `room_id` when loading topics
- Topics are filtered to only show those with discussions in the selected room

This doesn't fully work because:
- Analysis still runs globally
- Topics themselves are still global (just filtered in display)
- New analysis will still analyze all rooms

## Notes

- There are 183 discussions in General Chat, only 2 in Immersion
- 10 topics exist currently (all global)
- Backup script updated to backup all 3 databases (messenger_archive, synapse, mautrix_meta)
- Backups run every 6 hours via cron
