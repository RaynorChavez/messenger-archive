# Plan: Improve Reply Detection & Add Image Descriptions

## Overview

Two main features:
1. **Better reply context** - Include the quoted message when someone replies
2. **Image descriptions** - Process images through Gemini Vision, store descriptions, include in LLM context

Both features will improve:
- Virtual Chat (persona conversations)
- AI Profile Summaries (person analysis)

---

## Phase 1: Database Changes

**New table: `image_descriptions`**
```sql
CREATE TABLE image_descriptions (
    id SERIAL PRIMARY KEY,
    message_id INTEGER REFERENCES messages(id) ON DELETE CASCADE,
    media_id VARCHAR(255) NOT NULL UNIQUE,  -- The Matrix media ID
    description TEXT,                        -- Gemini-generated description
    ocr_text TEXT,                          -- Any text detected in image
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE   -- When Gemini processed it
);
```

**Modify `messages` table:**
```sql
ALTER TABLE messages ADD COLUMN message_type VARCHAR(20) DEFAULT 'text';
ALTER TABLE messages ADD COLUMN media_url VARCHAR(500);  -- mxc:// URL
```

---

## Phase 2: Archive Service - Capture Images

**File:** `archive-service/src/main.py`

1. Add `RoomMessageImage` event callback
2. Store image messages with `message_type='image'` and `media_url`
3. Queue images for background processing (or process inline)

**File:** `scripts/backfill_messages.py`
- Update to also capture historical image messages

---

## Phase 3: Image Description Service

**New file:** `api/src/services/image_description.py`

1. Fetch image from Synapse media store
2. Send to Gemini Vision API (model: gemini-3-flash-preview) with prompt:
   ```
   Describe this image concisely. If there's text, transcribe it.
   Format: [Description: ...] [Text: ...] (if any text present)
   ```
3. Store description in `image_descriptions` table
4. Can run as:
   - Background job (process queue)
   - On-demand when image is first referenced

---

## Phase 4: Include Replies in Context

**File:** `api/src/services/virtual_chat.py`

Modify `_format_message_section()` to include reply context:

```python
# Current format:
[PersonA]: Hello everyone

# New format with reply:
[PersonA]: Hello everyone

[PersonB] (replying to PersonA: "Hello everyone"):
Welcome back!
```

**File:** `api/src/services/ai.py`

Similar changes to `_format_messages_with_context()` for profile summaries.

---

## Phase 5: Include Images in Context

**File:** `api/src/services/virtual_chat.py`

When formatting messages:
```python
if msg.message_type == 'image':
    desc = get_image_description(msg.id)
    if desc:
        content = f"[[Image: {desc.description}]]"
        if desc.ocr_text:
            content += f" [[Text in image: {desc.ocr_text}]]"
    else:
        content = "[[sent an image]]"
```

**File:** `api/src/services/ai.py`

Same approach for profile summaries.

---

## Task Breakdown

| # | Task | Files | Status |
|---|------|-------|--------|
| 1 | Add `message_type` and `media_url` columns to messages | `db.py`, migration SQL | [x] |
| 2 | Create `image_descriptions` table | `db.py`, migration SQL | [x] |
| 3 | Update archive-service to capture image messages | `archive-service/src/main.py` | [x] |
| 4 | Update backfill script for images | `scripts/backfill_messages.py` | [x] |
| 5 | Create image description service | `api/src/services/image_description.py` | [x] |
| 6 | Add reply context to virtual chat | `api/src/services/virtual_chat.py` | [x] |
| 7 | Add reply context to AI summaries | `api/src/services/ai.py` | [x] |
| 8 | Add image descriptions to virtual chat context | `api/src/services/virtual_chat.py` | [x] |
| 9 | Add image descriptions to AI summary context | `api/src/routers/people.py` | [x] |
| 10 | API endpoint to process images | `api/src/routers/settings.py`, `api/src/main.py` | [x] |

---

## Example Output

**Virtual Chat Context (before):**
```
[Alice]: What do you think about this?
[Bob]: I agree with what you said earlier
[Alice]: sent an image
```

**Virtual Chat Context (after):**
```
[Alice]: What do you think about this?

[Bob] (replying to Alice: "What do you think about this?"):
I agree with what you said earlier

[Alice]: [[Image: A handwritten note with philosophical quotes about existentialism]] [[Text in image: "To be is to do" - Sartre]]
```
