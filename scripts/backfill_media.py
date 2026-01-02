#!/usr/bin/env python3
"""
Backfill media information from Synapse events to messenger_archive messages.

This script:
1. Queries Synapse event_json for image/video/audio/file messages
2. Updates the corresponding messages in messenger_archive with message_type and media_url
3. Creates image_descriptions records for images to be processed

Usage:
    python scripts/backfill_media.py [--limit N] [--dry-run]
    
Arguments:
    --limit N    Limit to N most recent media messages (default: 200 for local, 1000 for prod)
    --dry-run    Show what would be done without making changes
"""

import argparse
import json
import os
import sys
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor


def get_db_url():
    """Get database URL from environment."""
    return os.environ.get(
        "DATABASE_URL", 
        "postgresql://archive:philosophy123@localhost:5432/messenger_archive"
    )


def get_synapse_url():
    """Get Synapse database connection info.
    
    Note: In Docker, we connect directly to postgres, not pgbouncer,
    since pgbouncer only has messenger_archive configured.
    """
    # Check for explicit synapse URL
    synapse_url = os.environ.get("SYNAPSE_DATABASE_URL")
    if synapse_url:
        return synapse_url
    
    # Derive from main DB URL
    db_url = get_db_url()
    
    # If using pgbouncer, switch to direct postgres
    if "pgbouncer" in db_url:
        db_url = db_url.replace("pgbouncer:6432", "postgres:5432")
    
    # Replace database name
    if "/messenger_archive" in db_url:
        return db_url.replace("/messenger_archive", "/synapse")
    return db_url.rsplit("/", 1)[0] + "/synapse"


def get_media_events(synapse_conn, limit: int):
    """Get media events from Synapse."""
    with synapse_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT 
                event_id,
                json::text as event_json
            FROM event_json
            WHERE 
                json::text LIKE '%%"msgtype":"m.image"%%'
                OR json::text LIKE '%%"msgtype":"m.video"%%'
                OR json::text LIKE '%%"msgtype":"m.audio"%%'
                OR json::text LIKE '%%"msgtype":"m.file"%%'
            ORDER BY event_id DESC
            LIMIT %s
        """, (limit,))
        return cur.fetchall()


def parse_event(event_row):
    """Parse event JSON to extract media info."""
    try:
        event = json.loads(event_row['event_json'])
        content = event.get('content', {})
        msgtype = content.get('msgtype', '')
        
        # Map Matrix msgtype to our message_type
        type_map = {
            'm.image': 'image',
            'm.video': 'video',
            'm.audio': 'audio',
            'm.file': 'file',
        }
        
        message_type = type_map.get(msgtype)
        if not message_type:
            return None
            
        media_url = content.get('url')  # mxc:// URL
        
        return {
            'event_id': event_row['event_id'],
            'message_type': message_type,
            'media_url': media_url,
        }
    except Exception as e:
        print(f"Error parsing event {event_row['event_id']}: {e}")
        return None


def update_message(archive_conn, event_id: str, message_type: str, media_url: str, dry_run: bool):
    """Update message with media info and create image_description if needed."""
    with archive_conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Find the message
        cur.execute("""
            SELECT id, message_type, media_url 
            FROM messages 
            WHERE matrix_event_id = %s
        """, (event_id,))
        
        msg = cur.fetchone()
        if not msg:
            return False, "not_found"
        
        # Skip if already has correct type
        if msg['message_type'] == message_type and msg['media_url'] == media_url:
            return False, "already_set"
        
        if dry_run:
            return True, "would_update"
        
        # Update message
        cur.execute("""
            UPDATE messages 
            SET message_type = %s, media_url = %s
            WHERE id = %s
        """, (message_type, media_url, msg['id']))
        
        # Create image_description record if it's an image
        if message_type == 'image' and media_url:
            # Extract media_id from mxc://server/media_id
            parts = media_url.split('/')
            if len(parts) >= 4:
                media_id = parts[-1]
                
                # Check if already exists
                cur.execute("""
                    SELECT id FROM image_descriptions WHERE media_id = %s
                """, (media_id,))
                
                if not cur.fetchone():
                    cur.execute("""
                        INSERT INTO image_descriptions (message_id, media_id)
                        VALUES (%s, %s)
                        ON CONFLICT (media_id) DO NOTHING
                    """, (msg['id'], media_id))
        
        return True, "updated"


def main():
    parser = argparse.ArgumentParser(description='Backfill media info from Synapse to messenger_archive')
    parser.add_argument('--limit', type=int, default=200, help='Limit to N most recent media messages')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    args = parser.parse_args()
    
    print(f"Backfilling media info (limit: {args.limit}, dry_run: {args.dry_run})")
    print()
    
    # Connect to databases
    archive_url = get_db_url()
    synapse_url = get_synapse_url()
    
    print(f"Connecting to Synapse: {synapse_url.split('@')[1] if '@' in synapse_url else synapse_url}")
    synapse_conn = psycopg2.connect(synapse_url)
    
    print(f"Connecting to Archive: {archive_url.split('@')[1] if '@' in archive_url else archive_url}")
    archive_conn = psycopg2.connect(archive_url)
    
    # Get media events from Synapse
    print(f"\nFetching up to {args.limit} media events from Synapse...")
    events = get_media_events(synapse_conn, args.limit)
    print(f"Found {len(events)} media events")
    
    # Process each event
    stats = {
        'updated': 0,
        'already_set': 0,
        'not_found': 0,
        'would_update': 0,
        'errors': 0,
        'by_type': {'image': 0, 'video': 0, 'audio': 0, 'file': 0}
    }
    
    for event in events:
        parsed = parse_event(event)
        if not parsed:
            stats['errors'] += 1
            continue
        
        success, status = update_message(
            archive_conn,
            parsed['event_id'],
            parsed['message_type'],
            parsed['media_url'],
            args.dry_run
        )
        
        stats[status] += 1
        if success:
            stats['by_type'][parsed['message_type']] += 1
    
    if not args.dry_run:
        archive_conn.commit()
    
    # Print summary
    print("\n=== Summary ===")
    if args.dry_run:
        print(f"Would update: {stats['would_update']}")
    else:
        print(f"Updated: {stats['updated']}")
    print(f"Already set: {stats['already_set']}")
    print(f"Not found in archive: {stats['not_found']}")
    print(f"Parse errors: {stats['errors']}")
    print()
    print("By type:")
    for t, count in stats['by_type'].items():
        if count > 0:
            print(f"  {t}: {count}")
    
    # Show pending image processing count
    if not args.dry_run:
        with archive_conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM image_descriptions 
                WHERE processed_at IS NULL AND error IS NULL
            """)
            pending = cur.fetchone()[0]
            print(f"\nPending images to process: {pending}")
    
    synapse_conn.close()
    archive_conn.close()
    
    print("\nDone!")


if __name__ == '__main__':
    main()
