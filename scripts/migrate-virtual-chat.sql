-- Virtual Chat Migration
-- Run with: docker compose exec postgres psql -U archive -d messenger_archive -f /scripts/migrate-virtual-chat.sql

-- Virtual conversations table
CREATE TABLE IF NOT EXISTS virtual_conversations (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Virtual participants (people in a conversation)
CREATE TABLE IF NOT EXISTS virtual_participants (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES virtual_conversations(id) ON DELETE CASCADE,
    person_id INTEGER REFERENCES people(id) ON DELETE CASCADE,
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(conversation_id, person_id)
);

-- Virtual messages (user and agent messages)
CREATE TABLE IF NOT EXISTS virtual_messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES virtual_conversations(id) ON DELETE CASCADE,
    sender_type VARCHAR(20) NOT NULL CHECK (sender_type IN ('user', 'agent')),
    person_id INTEGER REFERENCES people(id) ON DELETE SET NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_virtual_messages_conv ON virtual_messages(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_virtual_participants_conv ON virtual_participants(conversation_id);
CREATE INDEX IF NOT EXISTS idx_virtual_participants_person ON virtual_participants(person_id);

-- Verify tables were created
SELECT 'virtual_conversations' as table_name, COUNT(*) as row_count FROM virtual_conversations
UNION ALL
SELECT 'virtual_participants', COUNT(*) FROM virtual_participants
UNION ALL
SELECT 'virtual_messages', COUNT(*) FROM virtual_messages;
