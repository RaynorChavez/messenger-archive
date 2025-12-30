-- =============================================================================
-- Messenger Archive - Database Initialization
-- =============================================================================
-- This script runs automatically when the Postgres container starts for the
-- first time. It creates the archive tables (Matrix/Bridge tables are managed
-- by Dendrite and mautrix-meta separately).

-- -----------------------------------------------------------------------------
-- People table
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS people (
    id              SERIAL PRIMARY KEY,
    matrix_user_id  TEXT UNIQUE NOT NULL,
    display_name    TEXT,
    avatar_url      TEXT,
    notes           TEXT,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- Rooms table
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rooms (
    id              SERIAL PRIMARY KEY,
    matrix_room_id  TEXT UNIQUE NOT NULL,
    name            TEXT,
    is_group        BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- Messages table
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS messages (
    id                      SERIAL PRIMARY KEY,
    matrix_event_id         TEXT UNIQUE NOT NULL,
    room_id                 INTEGER REFERENCES rooms(id) ON DELETE CASCADE,
    sender_id               INTEGER REFERENCES people(id) ON DELETE SET NULL,
    content                 TEXT,
    reply_to_message_id     INTEGER REFERENCES messages(id) ON DELETE SET NULL,
    timestamp               TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- Indexes
-- -----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_messages_room ON messages(room_id);
CREATE INDEX IF NOT EXISTS idx_messages_reply ON messages(reply_to_message_id);

-- Full-text search index
CREATE INDEX IF NOT EXISTS idx_messages_content_search 
ON messages USING gin(to_tsvector('english', coalesce(content, '')));

-- -----------------------------------------------------------------------------
-- Updated at trigger
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_people_updated_at
    BEFORE UPDATE ON people
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
