# Virtual Chat Implementation Plan

AI-powered group chat where Gemini agents roleplay as archived people based on their documented messages and chat style.

## Key Decisions

| Decision | Choice |
|----------|--------|
| Backend persistence | Persistent (conversations stored in DB) |
| Frontend persistence | Ephemeral (no conversation list, starts fresh each session) |
| Response behavior | All agents evaluate in parallel, each decides whether to respond |
| Persona context | ALL of person's messages + 3 before/after context (deduplicated) |
| Caching strategy | Gemini implicit caching (consistent prompt prefix per person) |
| Streaming | SSE with JSON events, interleaved chunks from multiple agents |
| Thinking indicator | Show per-agent "thinking" state while generating |
| 1:1 profile chat | Same UI as group chat, accessed via `/virtual-chat?id={conv_id}` |

---

## Database Schema

**File:** `scripts/migrate-virtual-chat.sql`

```sql
CREATE TABLE virtual_conversations (
  id SERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE virtual_participants (
  id SERIAL PRIMARY KEY,
  conversation_id INTEGER REFERENCES virtual_conversations(id) ON DELETE CASCADE,
  person_id INTEGER REFERENCES people(id) ON DELETE CASCADE,
  joined_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(conversation_id, person_id)
);

CREATE TABLE virtual_messages (
  id SERIAL PRIMARY KEY,
  conversation_id INTEGER REFERENCES virtual_conversations(id) ON DELETE CASCADE,
  sender_type VARCHAR(20) NOT NULL CHECK (sender_type IN ('user', 'agent')),
  person_id INTEGER REFERENCES people(id) ON DELETE SET NULL,
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_virtual_messages_conv ON virtual_messages(conversation_id, created_at);
CREATE INDEX idx_virtual_participants_conv ON virtual_participants(conversation_id);
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/virtual-chat/conversations` | Create conversation with participant IDs |
| `GET` | `/api/virtual-chat/conversations/{id}` | Get conversation with messages & participants |
| `POST` | `/api/virtual-chat/conversations/{id}/message` | Send message, returns SSE stream |

### SSE Event Format

All events are JSON with a `type` field:

```typescript
// User message saved
{ "type": "user_message", "id": 123, "content": "Hey @Yosh what do you think?" }

// Agent starts thinking
{ "type": "thinking", "person_id": 5, "display_name": "Yosh Tamura" }

// Agent text chunk (streaming)
{ "type": "chunk", "person_id": 5, "text": "I think" }
{ "type": "chunk", "person_id": 5, "text": " that's" }
{ "type": "chunk", "person_id": 5, "text": " interesting..." }

// Agent finished (empty content = chose not to respond)
{ "type": "agent_done", "person_id": 5, "message_id": 124 }

// All agents complete
{ "type": "complete" }

// Error
{ "type": "error", "message": "Rate limit exceeded" }
```

---

## Persona Prompt Template

```python
PERSONA_TEMPLATE = """You are roleplaying as {name} in a group chat conversation.

## Who You Are
{summary}

## How You Communicate
Below are ALL of {name}'s real messages from the archive, with surrounding context to show what they were responding to. Study their writing style carefully - their vocabulary, emoji usage, message length, language (English/Tagalog/mixed), and tone.

{messages_with_context}

## Instructions
- Write EXACTLY as {name} would write - match their style precisely
- You may respond naturally to the conversation, or choose not to respond at all
- If you have nothing to add, respond with just: [NO RESPONSE]
- If someone mentions you with @{name}, you should generally respond
- Keep responses natural length for this person (short if they write short, longer if they write long)
- Never break character or acknowledge you're an AI
- Use the same language patterns they use (English, Tagalog, code-switching, etc.)
"""
```

---

## Context Building

Each person's persona context includes:
1. System prompt with profile summary
2. ALL of their archived messages
3. 3 messages before and after each of their messages (for conversation context)
4. Deduplication of overlapping context windows

```
[STATIC - implicitly cached by Gemini]
├── System prompt (persona instructions)
├── Person's profile summary  
├── ALL of person's messages with context (always same order)
│
[DYNAMIC - appended fresh each request]
├── Virtual conversation history so far
└── New user message
```

### Message Format

```
--- Message 1 ---
  [Context before:]
    [2025-01-01 10:00] Alice: What do you think about...
    [2025-01-01 10:01] Bob: I believe that...
  >>> [2025-01-01 10:02] {PersonName}: Their actual message here
  [Context after:]
    [2025-01-01 10:03] Alice: That's interesting because...
    [2025-01-01 10:04] Charlie: I agree with...

--- Message 2 ---
  ...
```

---

## Architecture

### Parallel Agent Response Flow

```
User sends message
        │
        ▼
┌───────────────┐
│ Save user msg │
│ Parse @mentions│
└───────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│              For each participant (parallel)                   │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  1. Get/build persona context (cached in memory)         │  │
│  │     - Profile summary + all messages w/ context          │  │
│  │                                                          │  │
│  │  2. Send to Gemini with streaming                        │  │
│  │     - Static persona (Gemini implicit caching)           │  │
│  │     - Virtual conversation history                       │  │
│  │     - New user message                                   │  │
│  │                                                          │  │
│  │  3. Stream response chunks via SSE                       │  │
│  │     - [NO RESPONSE] = agent chose not to respond         │  │
│  └─────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────┐
│ SSE: complete │
└───────────────┘
```

### In-Memory Persona Cache

Cache built persona contexts to avoid rebuilding from DB every request:

```python
class PersonaCache:
    """In-memory cache for built persona contexts."""
    _cache: Dict[int, str] = {}  # person_id -> persona_context
    
    def get(self, person_id: int) -> Optional[str]: ...
    def set(self, person_id: int, context: str): ...
    def invalidate(self, person_id: int): ...  # Called when profile summary regenerated
```

---

## UI Layout

### Group Chat

```
┌─────────────────────────────────────────────────────────────┐
│  Virtual Chat                               [+ Add Person]  │
├─────────────────────────────────────────────────────────────┤
│  Chatting with: Yosh, Paulina, Juan                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ You:                                                 │   │
│  │ Hey everyone, what do you think about the 3BP?       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 🟢 Yosh is thinking...                              │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ [Avatar] Paulina:                                    │   │
│  │ omg i just finished reading it!! the dark forest    │   │
│  │ theory is so scary but like... makes sense??█       │   │  <- streaming
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 🟢 Juan is thinking...                              │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  [@] Type a message...                          [Send]      │
│  ┌─────────────┐                                            │
│  │ @Yosh       │  <- autocomplete dropdown                  │
│  │ @Paulina    │                                            │
│  │ @Juan       │                                            │
│  └─────────────┘                                            │
└─────────────────────────────────────────────────────────────┘
```

### 1:1 Profile Chat

Same UI, but:
- No @mention autocomplete needed (only one person)
- Show mini-profile card at top
- "[+ Add Person]" button allows converting to group chat

```
┌─────────────────────────────────────────────────────────────┐
│  Virtual Chat with Yosh Tamura              [+ Add Person]  │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────┐                   │
│  │ [Avatar]  Yosh Tamura                │                   │
│  │ "Writes thoughtful long-form..."     │  <- mini profile  │
│  └──────────────────────────────────────┘                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ... chat messages ...                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: Database & Models
- [ ] Create `scripts/migrate-virtual-chat.sql`
- [ ] Add SQLAlchemy models to `api/src/db.py`:
  - `VirtualConversation`
  - `VirtualParticipant`
  - `VirtualMessage`

### Phase 2: Pydantic Schemas
- [ ] Create `api/src/schemas/virtual_chat.py`:
  - `CreateConversationRequest`
  - `ConversationResponse`
  - `VirtualMessageResponse`
  - `SendMessageRequest`
  - SSE event types

### Phase 3: Persona Builder
- [ ] Create `api/src/services/virtual_chat.py`:
  - `PersonaCache` class (in-memory cache with invalidation)
  - `PersonaBuilder` class:
    - `build_persona_context(person_id)` - builds full context
    - `build_messages_with_context(person_id)` - all messages + 3 before/after, deduplicated
    - `format_message_section(msg, before, after)` - formats single message with context

### Phase 4: Agent Service
- [ ] Add to `api/src/services/virtual_chat.py`:
  - `VirtualChatService` class:
    - `create_conversation(participant_ids)`
    - `get_conversation(id)`
    - `process_message(conversation_id, content)` - returns async generator of SSE events
    - `_stream_agent_response(person_id, history, new_message)` - streams single agent
    - `_interleave_streams(streams)` - merges multiple async generators

### Phase 5: SSE Router
- [ ] Create `api/src/routers/virtual_chat.py`:
  - `POST /conversations` - create conversation
  - `GET /conversations/{id}` - get conversation with messages
  - `POST /conversations/{id}/message` - send message, return SSE stream
- [ ] Add to `api/src/routers/__init__.py`
- [ ] Register in `api/src/main.py`

### Phase 6: Cache Invalidation
- [ ] Update `api/src/routers/people.py`:
  - After profile summary regeneration, call `persona_cache.invalidate(person_id)`

### Phase 7: Frontend - Chat UI
- [ ] Create `web/src/app/virtual-chat/page.tsx`:
  - Participant selector (if no conversation ID)
  - Chat message list
  - SSE consumption with interleaved streaming
  - Thinking indicators per agent
  - @mention autocomplete in input (for group chats)
- [ ] Add types to `web/src/lib/api.ts`:
  - `VirtualConversation`
  - `VirtualMessage`
  - `VirtualParticipant`
  - API functions

### Phase 8: Frontend - Profile Integration
- [ ] Update `web/src/app/people/[id]/page.tsx`:
  - Add "Virtual Chat" button
  - On click: create 1:1 conversation, redirect to `/virtual-chat?id={conv_id}`

### Phase 9: Navigation
- [ ] Update `web/src/components/layout/sidebar.tsx`:
  - Add "Virtual Chat" link

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `scripts/migrate-virtual-chat.sql` | Create | Database migration |
| `api/src/db.py` | Modify | Add 3 SQLAlchemy models |
| `api/src/schemas/virtual_chat.py` | Create | Pydantic schemas |
| `api/src/services/virtual_chat.py` | Create | PersonaBuilder, VirtualChatService, PersonaCache |
| `api/src/routers/virtual_chat.py` | Create | API endpoints with SSE |
| `api/src/routers/__init__.py` | Modify | Export new router |
| `api/src/main.py` | Modify | Register router |
| `api/src/routers/people.py` | Modify | Add cache invalidation |
| `web/src/lib/api.ts` | Modify | Add types and API functions |
| `web/src/app/virtual-chat/page.tsx` | Create | Chat UI |
| `web/src/app/people/[id]/page.tsx` | Modify | Add Virtual Chat button |
| `web/src/components/layout/sidebar.tsx` | Modify | Add nav link |

---

## Token Estimates

Based on current archive data:

| Person | Messages | Est. Tokens (with context) |
|--------|----------|---------------------------|
| Most active (Yosh) | 571 | ~48,000 |
| Medium activity | ~200 | ~17,000 |
| Low activity | ~50 | ~4,500 |
| Minimal (1-2 msgs) | 1-2 | ~100-200 |

All active users exceed the 4,096 token minimum for Gemini's implicit caching benefit.

---

## Future Enhancements

1. **Conversation history UI** - Show past conversations (currently backend-only persistence)
2. **Export conversations** - Download virtual chat transcripts
3. **Persona fine-tuning** - Adjust persona traits (formality, verbosity, etc.)
4. **Multi-turn memory** - Agents remember previous virtual conversations
5. **Topic injection** - Seed conversations with specific topics from the archive
