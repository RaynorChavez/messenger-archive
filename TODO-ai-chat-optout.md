# AI Virtual Chat Opt-Out Feature

## Overview
Allow people to opt-out their digital persona from the AI virtual chat. Opt-out requires setting a password; only that password can re-enable the persona.

## Status: Complete (Local) - Ready for Production Deploy

---

## Database Changes

**Add to `people` table:**
```sql
ALTER TABLE people ADD COLUMN ai_chat_enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE people ADD COLUMN ai_chat_password_hash VARCHAR(255) NULL;
```

---

## Backend Changes

### 1. Update `api/src/db.py`
- [x] Add `ai_chat_enabled` (Boolean, default True)
- [x] Add `ai_chat_password_hash` (String, nullable)

### 2. New endpoints in `api/src/routers/people.py`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/people/{id}/ai-chat/disable` | POST | Disable AI chat, requires `password` in body. Hashes and stores password. |
| `/people/{id}/ai-chat/enable` | POST | Re-enable AI chat, requires `password` in body. Verifies against stored hash. |
| `/people/{id}/ai-chat/status` | GET | Returns `{ enabled: bool, has_password: bool }` |

### 3. Update virtual chat service
- [x] Filter out people where `ai_chat_enabled = False` from available personas
- [x] Return error if user tries to chat with opted-out persona

---

## Frontend Changes

### 1. Update `web/src/app/people/[id]/page.tsx`
- [x] Add "AI Chat Status" section on profile page
- [x] Show toggle/button based on current status:
  - If enabled: "Disable AI Persona" button → opens password prompt modal
  - If disabled: "Enable AI Persona" button → opens password verification modal

### 2. New component: `AIPersonaModal`
- [x] For disable: password + confirm password fields
- [x] For enable: password field only
- [x] Show error if password incorrect

### 3. Update `web/src/lib/api.ts`
- [x] Add `people.disableAIChat(id, password)`
- [x] Add `people.enableAIChat(id, password)`
- [x] Add `people.aiChatStatus(id)`

### 4. Update virtual chat page
- [x] Filter out opted-out people from persona selection

---

## Security Notes
- Use bcrypt for password hashing
- No password recovery (intentional - only the person who set it can undo)
- Password is persona-specific, not tied to app auth

---

## Migration Script

File: `scripts/migrate-ai-chat-optout.sql`

```sql
-- AI Chat Opt-Out Migration
-- Run with:
--   Local: docker exec -i archive-postgres psql -U archive -d messenger_archive < scripts/migrate-ai-chat-optout.sql
--   Prod:  ssh ubuntu@98.86.15.121 "docker exec -i archive-postgres psql -U archive -d messenger_archive" < scripts/migrate-ai-chat-optout.sql

ALTER TABLE people ADD COLUMN IF NOT EXISTS ai_chat_enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE people ADD COLUMN IF NOT EXISTS ai_chat_password_hash VARCHAR(255) NULL;

-- Verify
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns 
WHERE table_name = 'people' AND column_name IN ('ai_chat_enabled', 'ai_chat_password_hash');
```

---

## Implementation Order

1. [x] Create migration script
2. [x] Update db.py models
3. [x] Add backend endpoints
4. [x] Update virtual chat service to filter opted-out personas
5. [x] Update frontend API functions
6. [x] Add AI persona modal component
7. [x] Update person profile page
8. [x] Update virtual chat page
9. [x] Test locally
10. [ ] Deploy to production
