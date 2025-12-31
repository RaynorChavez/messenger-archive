-- Migration script for incremental analysis feature
-- Run this on existing databases to add the new columns

-- Add new columns to discussion_analysis_runs
ALTER TABLE discussion_analysis_runs 
ADD COLUMN IF NOT EXISTS mode VARCHAR(20) DEFAULT 'full',
ADD COLUMN IF NOT EXISTS start_message_id INTEGER,
ADD COLUMN IF NOT EXISTS end_message_id INTEGER,
ADD COLUMN IF NOT EXISTS context_start_message_id INTEGER,
ADD COLUMN IF NOT EXISTS new_messages_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS context_messages_count INTEGER DEFAULT 0;

-- Update existing completed runs to have end_message_id set
-- This finds the max message ID that was analyzed in each completed run
UPDATE discussion_analysis_runs r
SET end_message_id = (
    SELECT MAX(m.id)
    FROM messages m
    JOIN discussion_messages dm ON dm.message_id = m.id
    JOIN discussions d ON d.id = dm.discussion_id
    WHERE d.analysis_run_id = r.id
)
WHERE r.status = 'completed' AND r.end_message_id IS NULL;

-- Verify
SELECT id, status, mode, end_message_id, discussions_found 
FROM discussion_analysis_runs 
ORDER BY id DESC 
LIMIT 5;
