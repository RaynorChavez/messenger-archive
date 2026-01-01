# Multi-Room Support Plan

## Overview

Add support for multiple group chats with:
- Room selector dropdown in header
- Unified people profiles with per-room breakdowns
- URL-based room routing (`/rooms/:id/...`)
- Historical FB archive import capability

**Rooms to support:**
1. General Chat - Manila Dialectics Society (existing)
2. Immersion - Manila Dialectics Society (new)

---

## Phase 1: Database Schema Changes

### 1.1 Add `room_members` table

Tracks which people are in which rooms with per-room stats.

```sql
CREATE TABLE room_members (
  id SERIAL PRIMARY KEY,
  room_id INTEGER REFERENCES rooms(id) ON DELETE CASCADE,
  person_id INTEGER REFERENCES people(id) ON DELETE CASCADE,
  first_seen_at TIMESTAMP WITH TIME ZONE,  -- first message in this room
  last_seen_at TIMESTAMP WITH TIME ZONE,   -- last message in this room
  message_count INTEGER DEFAULT 0,          -- cached count for this room
  UNIQUE(room_id, person_id)
);

CREATE INDEX idx_room_members_room ON room_members(room_id);
CREATE INDEX idx_room_members_person ON room_members(person_id);
```

### 1.2 Add room metadata columns to `rooms`

```sql
ALTER TABLE rooms ADD COLUMN avatar_url TEXT;
ALTER TABLE rooms ADD COLUMN description TEXT;
ALTER TABLE rooms ADD COLUMN display_order INTEGER DEFAULT 0;  -- for sorting in dropdown
```

### 1.3 Backfill `room_members` from existing messages

```sql
INSERT INTO room_members (room_id, person_id, first_seen_at, last_seen_at, message_count)
SELECT 
  room_id,
  sender_id,
  MIN(timestamp),
  MAX(timestamp),
  COUNT(*)
FROM messages
WHERE sender_id IS NOT NULL AND room_id IS NOT NULL
GROUP BY room_id, sender_id;
```

### 1.4 Add source tracking for future imports

```sql
ALTER TABLE messages ADD COLUMN source TEXT DEFAULT 'bridge';
-- Values: 'bridge' (live from Matrix), 'fb_import' (historical import)
```

---

## Phase 2: Backend API Changes

### 2.1 New Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /api/rooms` | GET | List all rooms for dropdown selector |
| `GET /api/rooms/:id` | GET | Get room details with stats |

**Response for `GET /api/rooms`:**
```json
{
  "rooms": [
    {
      "id": 1,
      "name": "General Chat - Manila Dialectics Society",
      "avatar_url": null,
      "message_count": 6000,
      "member_count": 77,
      "last_message_at": "2024-12-31T10:00:00Z",
      "display_order": 0
    }
  ]
}
```

### 2.2 Modified Endpoints (add `room_id` filter)

All these endpoints get an optional `?room_id=X` query parameter:

| Endpoint | Notes |
|----------|-------|
| `GET /api/messages` | Filter messages to room |
| `GET /api/stats` | Room-specific stats |
| `GET /api/threads` | Filter threads to room |
| `GET /api/search` | Search within room |
| `GET /api/discussions` | Filter discussions to room |
| `GET /api/topics` | Filter topics to room |

**Behavior:**
- If `room_id` is provided, filter to that room
- If `room_id` is omitted, return data from all rooms (for backward compatibility in people profiles)

### 2.3 People Endpoints (unified + room breakdown)

| Endpoint | Description |
|----------|-------------|
| `GET /api/people` | List all people (unchanged, shows unified data) |
| `GET /api/people/:id` | Get person with unified stats |
| `GET /api/people/:id/rooms` | **NEW**: Get list of rooms this person is in with per-room stats |
| `GET /api/people/:id/messages?room_id=X` | Filter messages to specific room (optional) |
| `GET /api/people/:id/activity?room_id=X` | Activity chart for specific room (optional) |

**Response for `GET /api/people/:id/rooms`:**
```json
{
  "rooms": [
    {
      "room_id": 1,
      "room_name": "General Chat - Manila Dialectics Society",
      "message_count": 65,
      "first_seen_at": "2024-01-15T10:00:00Z",
      "last_seen_at": "2024-12-31T10:00:00Z"
    },
    {
      "room_id": 2,
      "room_name": "Immersion - Manila Dialectics Society",
      "message_count": 12,
      "first_seen_at": "2024-03-01T10:00:00Z",
      "last_seen_at": "2024-12-30T10:00:00Z"
    }
  ]
}
```

---

## Phase 3: Frontend Changes

### 3.1 URL Structure

**New room-scoped routes:**
```
/rooms/:roomId/messages
/rooms/:roomId/threads  
/rooms/:roomId/discussions
/rooms/:roomId/search
/rooms/:roomId/topics
/rooms/:roomId/stats       # Dashboard for specific room
```

**Redirects:**
```
/                  -> /rooms/:firstRoomId/stats
/messages          -> /rooms/:firstRoomId/messages
/threads           -> /rooms/:firstRoomId/threads
/discussions       -> /rooms/:firstRoomId/discussions
/search            -> /rooms/:firstRoomId/search
/topics            -> /rooms/:firstRoomId/topics
```

**Unchanged routes (not room-scoped):**
```
/people                 # All people (unified view)
/people/:id             # Person profile (unified with room breakdown)
/virtual-chat           # Virtual chat (not room-scoped)
/database               # Database viewer
/settings               # Settings
/login                  # Login
```

### 3.2 Room Selector Component (Header Dropdown)

**Location:** Header bar, after logo

**Design:**
```
┌─────────────────────────────────────────────────────────────────────┐
│  [Logo]  [General Chat - Manila Dialectics Society ▾]  [Search] [☀️] │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                   ┌──────────────────────────────────────┐
                   │ ✓ General Chat - Manila Dialectics   │
                   │   Immersion - Manila Dialectics Soc. │
                   └──────────────────────────────────────┘
```

**Behavior:**
- Shows current room name with dropdown arrow
- Only visible on room-scoped pages (`/rooms/:id/...`)
- Hidden on non-room pages (`/people`, `/virtual-chat`, etc.)
- Clicking opens list of rooms
- Selecting a room navigates to same page type in new room context
  - e.g., `/rooms/1/messages` -> `/rooms/2/messages`
- Checkmark on currently selected room

### 3.3 Sidebar Navigation Updates

**When on room-scoped page (`/rooms/:id/...`):**
- Sidebar links include room context
- Dashboard -> `/rooms/:id/stats`
- Messages -> `/rooms/:id/messages`
- Threads -> `/rooms/:id/threads`
- Discussions -> `/rooms/:id/discussions`
- Search -> `/rooms/:id/search`
- Topics -> `/rooms/:id/topics`

**When on non-room page (`/people`, `/virtual-chat`, etc.):**
- Sidebar links go to first room by default
- Or remember last selected room in localStorage

### 3.4 People Profile Changes

**Existing unified view (keep as-is):**
- Stats show combined across all rooms
- Messages show all rooms by default

**Add room breakdown section:**
```
┌─────────────────────────────────────────────────────────────┐
│  Raynor Chavez                                              │
│  77 messages · Last active Dec 31                           │
├─────────────────────────────────────────────────────────────┤
│  Rooms                                                      │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ General Chat - Manila Dialectics Society              │ │
│  │ 65 messages · Joined Jan 2024                         │ │
│  └───────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ Immersion - Manila Dialectics Society                 │ │
│  │ 12 messages · Joined Mar 2024                         │ │
│  └───────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│  Messages                              [All Rooms ▾]        │
│  ───────────────────────────────────────────────────────── │
│  (messages list, filterable by room)                        │
└─────────────────────────────────────────────────────────────┘
```

**Changes:**
- Add "Rooms" section with cards showing per-room stats
- Add room filter dropdown above messages list
- Activity chart can filter by room via dropdown

### 3.5 Dashboard Changes

**Current:** Single aggregate stats view

**New:** Per-room dashboard at `/rooms/:id/stats`
- Stats specific to selected room
- Activity chart for selected room
- Recent messages from selected room
- Top participants in selected room

---

## Phase 4: Archive Service - Monitor Second Room

### 4.1 Current Setup

The archive service monitors Matrix rooms and stores messages. Currently configured for one room.

### 4.2 Changes Needed

The archive service should automatically pick up new rooms when messages arrive. Need to verify:

1. **Room auto-discovery**: When a message arrives from a new room, create room record
2. **Room name sync**: Fetch room name from Matrix state events
3. **Member tracking**: Update `room_members` table when messages arrive

### 4.3 Configuration

Check `archive-service` config to ensure it's monitoring all rooms the bot user is in, not just a hardcoded room ID.

**Files to check:**
- `archive-service/src/main.py` or similar
- Any room ID configuration

---

## Phase 5: Historical FB Import (Future)

### 5.1 Import endpoint

```
POST /api/import/facebook
Content-Type: multipart/form-data
Body: { room_id: number, file: JSON file }
```

### 5.2 FB JSON format

Facebook exports as `message_*.json` files:
```json
{
  "participants": [
    {"name": "Raynor Chavez"}
  ],
  "messages": [
    {
      "sender_name": "Raynor Chavez",
      "timestamp_ms": 1234567890000,
      "content": "Hello world",
      "type": "Generic",
      "photos": [...],
      "reactions": [...]
    }
  ],
  "title": "Group Chat Name",
  "thread_path": "inbox/groupchat_123"
}
```

### 5.3 Import flow

1. Upload JSON file(s) for a room
2. Parse messages from JSON
3. Match participants to existing `people` by:
   - `fb_name` field if set
   - `display_name` fuzzy match
   - Create new person if no match
4. Insert messages with `source = 'fb_import'`
5. Update `room_members` stats
6. Handle duplicates (skip if similar timestamp + sender + content)

### 5.4 Import UI

Add to Settings or Database page:
- Room selector (which room to import into)
- File upload for JSON
- Progress indicator
- Import log/results

---

## Implementation Order

| # | Phase | Task | Effort | Priority |
|---|-------|------|--------|----------|
| 1 | 1.1 | Database migration (room_members table) | 30min | P0 |
| 2 | 1.2 | Add room metadata columns | 15min | P0 |
| 3 | 1.3 | Backfill room_members | 15min | P0 |
| 4 | 1.4 | Add source column to messages | 10min | P1 |
| 5 | 4.* | Configure archive service for second room | 1hr | P0 |
| 6 | 2.1 | New API endpoints (rooms list/detail) | 1hr | P0 |
| 7 | 2.2 | Add room_id filter to existing endpoints | 2hr | P0 |
| 8 | 2.3 | People endpoints with room breakdown | 1hr | P1 |
| 9 | 3.1 | Room selector dropdown component | 1hr | P0 |
| 10 | 3.2 | Update routing to /rooms/:id/... | 2hr | P0 |
| 11 | 3.3 | Update sidebar for room context | 1hr | P0 |
| 12 | 3.4 | People profile room breakdown UI | 2hr | P1 |
| 13 | 3.5 | Dashboard per-room stats | 1hr | P1 |
| 14 | 5.* | FB import feature | 4hr | P2 |

**Total estimate: ~16-18 hours**

**Priority legend:**
- P0: Required for basic multi-room support
- P1: Important for full feature set
- P2: Future enhancement

---

## File Changes Summary

### Backend (api/)

**New files:**
- `src/routers/rooms.py` - Room endpoints
- `src/schemas/room.py` - Room Pydantic models

**Modified files:**
- `src/db.py` - Add RoomMember model
- `src/routers/messages.py` - Add room_id filter
- `src/routers/stats.py` - Add room_id filter
- `src/routers/threads.py` - Add room_id filter
- `src/routers/search.py` - Add room_id filter
- `src/routers/discussions.py` - Add room_id filter
- `src/routers/topics.py` - Add room_id filter
- `src/routers/people.py` - Add room breakdown endpoint
- `src/main.py` - Register rooms router

### Frontend (web/)

**New files:**
- `src/components/room-selector.tsx` - Dropdown component
- `src/app/rooms/[roomId]/layout.tsx` - Room context layout
- `src/app/rooms/[roomId]/stats/page.tsx` - Room dashboard
- `src/app/rooms/[roomId]/messages/page.tsx` - Room messages
- `src/app/rooms/[roomId]/threads/page.tsx` - Room threads
- `src/app/rooms/[roomId]/discussions/page.tsx` - Room discussions
- `src/app/rooms/[roomId]/search/page.tsx` - Room search
- `src/app/rooms/[roomId]/topics/page.tsx` - Room topics

**Modified files:**
- `src/lib/api.ts` - Add room endpoints, room_id params
- `src/components/layout/header.tsx` - Add room selector
- `src/components/layout/sidebar.tsx` - Room-aware links
- `src/app/page.tsx` - Redirect to first room
- `src/app/messages/page.tsx` - Redirect to room
- `src/app/people/[id]/page.tsx` - Add room breakdown section

### Database

**Migration file:**
- `scripts/migrate-multi-room.sql`

### Archive Service

**Modified files:**
- Check room monitoring configuration
- Ensure room auto-creation on new messages

---

## Testing Checklist

- [ ] Database migration runs without errors
- [ ] Existing data is preserved
- [ ] room_members backfill is accurate
- [ ] Archive service picks up messages from new room
- [ ] Room selector shows all rooms
- [ ] Switching rooms updates URL and content
- [ ] Sidebar links maintain room context
- [ ] People profiles show unified stats
- [ ] People profiles show per-room breakdown
- [ ] Message filtering by room works
- [ ] Search within room works
- [ ] Discussions filtered by room
- [ ] All existing functionality still works
