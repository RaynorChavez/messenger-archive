-- AI Chat Opt-Out Migration
-- Adds columns for persona opt-out with password protection
--
-- Run with:
--   Local: docker exec -i archive-postgres psql -U archive -d messenger_archive < scripts/migrate-ai-chat-optout.sql
--   Prod:  ssh ubuntu@98.86.15.121 "docker exec -i archive-postgres psql -U archive -d messenger_archive" < scripts/migrate-ai-chat-optout.sql

ALTER TABLE people ADD COLUMN IF NOT EXISTS ai_chat_enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE people ADD COLUMN IF NOT EXISTS ai_chat_password_hash VARCHAR(255) NULL;

-- Verify
SELECT 'Migration complete. Columns added:';
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns 
WHERE table_name = 'people' AND column_name IN ('ai_chat_enabled', 'ai_chat_password_hash');
