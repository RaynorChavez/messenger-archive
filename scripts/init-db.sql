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
-- Vector Embeddings (Semantic Search)
-- -----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS embeddings (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,  -- 'message', 'discussion', 'person', 'topic'
    entity_id INTEGER NOT NULL,
    content_hash VARCHAR(64),          -- SHA256 hash for change detection
    embedding vector(768),             -- Gemini text-embedding-004 = 768 dimensions
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(entity_type, entity_id)
);

-- Index for vector similarity search (IVFFlat)
CREATE INDEX IF NOT EXISTS idx_embeddings_vector 
ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Index for entity lookups
CREATE INDEX IF NOT EXISTS idx_embeddings_entity 
ON embeddings (entity_type, entity_id);

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
