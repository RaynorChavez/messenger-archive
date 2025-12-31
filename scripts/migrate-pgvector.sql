-- =============================================================================
-- Semantic Search Migration
-- =============================================================================
-- Run this after switching to pgvector/pgvector:pg15 image
-- 
-- Usage:
--   docker compose exec postgres psql -U archive -d messenger_archive -f /docker-entrypoint-initdb.d/migrate-pgvector.sql

-- Enable vector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create embeddings table
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
-- Lists = sqrt(n) is a good starting point; 100 for ~10k records
CREATE INDEX IF NOT EXISTS idx_embeddings_vector 
ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Index for entity lookups
CREATE INDEX IF NOT EXISTS idx_embeddings_entity 
ON embeddings (entity_type, entity_id);

-- Confirm success
DO $$
BEGIN
    RAISE NOTICE 'pgvector migration completed successfully!';
    RAISE NOTICE 'Embeddings table created with vector(768) column';
END $$;
