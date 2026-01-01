-- Multi-Room Support Migration
-- This migration adds support for multiple rooms with per-room member stats
-- 
-- Run with: docker compose exec postgres psql -U archive -d messenger_archive -f /scripts/migrate-multi-room.sql
-- Or copy/paste into psql

BEGIN;

-- =============================================================================
-- 1. Add metadata columns to rooms table
-- =============================================================================

-- Add avatar_url if not exists
DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'rooms' AND column_name = 'avatar_url') THEN
        ALTER TABLE rooms ADD COLUMN avatar_url TEXT;
    END IF;
END $$;

-- Add description if not exists
DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'rooms' AND column_name = 'description') THEN
        ALTER TABLE rooms ADD COLUMN description TEXT;
    END IF;
END $$;

-- Add display_order for sorting in dropdown
DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'rooms' AND column_name = 'display_order') THEN
        ALTER TABLE rooms ADD COLUMN display_order INTEGER DEFAULT 0;
    END IF;
END $$;

-- =============================================================================
-- 2. Create room_members table for per-room stats
-- =============================================================================

CREATE TABLE IF NOT EXISTS room_members (
    id SERIAL PRIMARY KEY,
    room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    first_seen_at TIMESTAMP WITH TIME ZONE,
    last_seen_at TIMESTAMP WITH TIME ZONE,
    message_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(room_id, person_id)
);

-- Create indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_room_members_room ON room_members(room_id);
CREATE INDEX IF NOT EXISTS idx_room_members_person ON room_members(person_id);
CREATE INDEX IF NOT EXISTS idx_room_members_message_count ON room_members(message_count DESC);

-- =============================================================================
-- 3. Add source column to messages for import tracking
-- =============================================================================

DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'messages' AND column_name = 'source') THEN
        ALTER TABLE messages ADD COLUMN source TEXT DEFAULT 'bridge';
    END IF;
END $$;

-- =============================================================================
-- 4. Backfill room_members from existing messages
-- =============================================================================

-- Insert room membership data derived from messages
-- This aggregates message stats per (room, person) pair
INSERT INTO room_members (room_id, person_id, first_seen_at, last_seen_at, message_count)
SELECT 
    room_id,
    sender_id,
    MIN(timestamp),
    MAX(timestamp),
    COUNT(*)
FROM messages
WHERE sender_id IS NOT NULL AND room_id IS NOT NULL
GROUP BY room_id, sender_id
ON CONFLICT (room_id, person_id) DO UPDATE SET
    first_seen_at = LEAST(room_members.first_seen_at, EXCLUDED.first_seen_at),
    last_seen_at = GREATEST(room_members.last_seen_at, EXCLUDED.last_seen_at),
    message_count = EXCLUDED.message_count;

-- =============================================================================
-- 5. Set initial display_order based on room id
-- =============================================================================

UPDATE rooms SET display_order = id WHERE display_order = 0 OR display_order IS NULL;

COMMIT;

-- =============================================================================
-- Verification queries (run these to verify migration succeeded)
-- =============================================================================

-- Check room_members was populated
-- SELECT 
--     r.name as room_name,
--     COUNT(rm.id) as member_count,
--     SUM(rm.message_count) as total_messages
-- FROM rooms r
-- LEFT JOIN room_members rm ON r.id = rm.room_id
-- GROUP BY r.id, r.name;

-- Check rooms have new columns
-- SELECT id, name, avatar_url, description, display_order FROM rooms;
