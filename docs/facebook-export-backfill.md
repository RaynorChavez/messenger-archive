# Facebook Export Backfill Plan

## Goal
Import full chat history from Facebook data export into the archive database, linking with existing Matrix-bridged data.

## Current State
- ~470 messages from "General Chat - Manila Dialectics Society" synced via mautrix-meta bridge
- Bridge has a 10,000 message limit but Messenger API only returned ~470
- Facebook data export requested and ready for download

## Data Linking Strategy

### User Matching
Matrix user IDs contain the Facebook ID:
```
@meta_100000040219220:archive.local → Facebook ID: 100000040219220
```

The import script will:
1. Extract Facebook ID from existing `people.matrix_user_id`
2. Match Facebook export participants by their Facebook ID
3. Link imported messages to existing person records

### Message Deduplication
To avoid duplicates between bridge-synced and imported messages:
- Hash: `sha256(sender_fb_id + timestamp + content)`
- Skip import if hash exists in database
- Or compare by timestamp + sender + content prefix

### Reply Linking
Facebook export includes reply metadata. Match replies by:
1. Find original message by timestamp + sender + content
2. Link `reply_to_message_id` to matched message
3. Flag unmatched replies for manual review (if any)

## Database Schema Changes Needed
```sql
ALTER TABLE messages ADD COLUMN import_source VARCHAR(20) DEFAULT 'bridge';
-- Values: 'bridge' (from mautrix-meta), 'fb_export' (from Facebook download)

ALTER TABLE messages ADD COLUMN fb_message_id VARCHAR(255);
-- Store Facebook's message ID for dedup and reply matching
```

## Import Script Location
`scripts/import_fb_export.py`

### Usage
```bash
# Extract Facebook download ZIP first
unzip facebook-yourname.zip -d ~/fb-export

# Run import (filter to philosophy chat only)
python scripts/import_fb_export.py \
  --export-path ~/fb-export/your_facebook_activity/messages/inbox \
  --chat-name "ManilaDial" \
  --db-url postgresql://archive:archivepass123@localhost:5432/messenger_archive
```

## Import Script Requirements
- Parse Facebook JSON message format
- Handle different message types (text, photos, reactions, etc.)
- Convert Facebook timestamps (milliseconds) to datetime
- Match/create person records
- Link replies where possible
- Mark imported messages with `import_source = 'fb_export'`

## Facebook Export JSON Structure
```
messages/inbox/chatname_abc123/
├── message_1.json
├── message_2.json  (if >10k messages)
├── photos/
└── videos/
```

Each message JSON contains:
```json
{
  "sender_name": "John Doe",
  "timestamp_ms": 1609459200000,
  "content": "Hello!",
  "type": "Generic",
  "reactions": [...],
  "reply_to": {...}
}
```

## Post-Import
1. Run backfill script to refresh archive from Synapse (catches any missed bridge messages)
2. Verify message counts match expected totals
3. Test search across imported + bridged messages
4. New messages continue flowing via bridge normally

## Notes
- Facebook export may have encoding issues (UTF-8 escaped as Latin-1) - script must handle this
- Photos/media from export could be imported later if needed
- Reactions could be stored in a separate table if desired
