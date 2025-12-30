#!/usr/bin/env python3
"""
Backfill script - Pulls messages from Synapse database into archive database.

Usage:
    docker compose exec api python /app/scripts/backfill.py [--room-filter "room name"]
    
Or run directly:
    python scripts/backfill.py --room-filter "General Chat"
"""

import argparse
import json
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Database URLs
SYNAPSE_DB_URL = "postgresql://archive:archivepass123@postgres:5432/synapse"
ARCHIVE_DB_URL = "postgresql://archive:archivepass123@postgres:5432/messenger_archive"


def get_synapse_messages(synapse_db, room_filter=None, limit=10000):
    """Fetch messages from Synapse database."""
    
    # Get rooms first
    rooms_query = """
        SELECT room_id, name 
        FROM room_stats_state 
        WHERE name IS NOT NULL
    """
    rooms = synapse_db.execute(text(rooms_query)).fetchall()
    
    room_map = {r[0]: r[1] for r in rooms}
    
    # Filter rooms if specified
    if room_filter:
        room_map = {k: v for k, v in room_map.items() if room_filter.lower() in v.lower()}
    
    if not room_map:
        print(f"No rooms found matching filter: {room_filter}")
        return []
    
    print(f"Found {len(room_map)} rooms to backfill:")
    for room_id, name in room_map.items():
        print(f"  - {name} ({room_id})")
    
    # Get messages from those rooms
    messages = []
    for room_id, room_name in room_map.items():
        msg_query = """
            SELECT 
                e.event_id,
                e.room_id,
                e.sender,
                e.origin_server_ts,
                ec.json
            FROM events e
            JOIN event_json ec ON e.event_id = ec.event_id
            WHERE e.room_id = :room_id
            AND e.type = 'm.room.message'
            ORDER BY e.origin_server_ts ASC
            LIMIT :limit
        """
        result = synapse_db.execute(
            text(msg_query), 
            {"room_id": room_id, "limit": limit}
        ).fetchall()
        
        for row in result:
            event_id, room_id, sender, ts, json_str = row
            try:
                event_json = json.loads(json_str)
                content = event_json.get("content", {})
                body = content.get("body", "")
                
                # Get reply info
                reply_to = None
                relates_to = content.get("m.relates_to", {})
                if relates_to.get("m.in_reply_to"):
                    reply_to = relates_to["m.in_reply_to"].get("event_id")
                
                messages.append({
                    "event_id": event_id,
                    "room_id": room_id,
                    "room_name": room_name,
                    "sender": sender,
                    "content": body,
                    "timestamp": datetime.fromtimestamp(ts / 1000),
                    "reply_to_event_id": reply_to
                })
            except Exception as e:
                print(f"Error parsing message {event_id}: {e}")
    
    return messages


def get_sender_profile(synapse_db, user_id):
    """Get display name and avatar for a user from Synapse."""
    # Extract localpart from full Matrix ID (@user:domain -> user)
    localpart = user_id.split(":")[0].lstrip("@") if ":" in user_id else user_id
    
    query = """
        SELECT displayname, avatar_url FROM profiles WHERE user_id = :user_id
    """
    result = synapse_db.execute(text(query), {"user_id": localpart}).fetchone()
    
    display_name = result[0] if result else None
    avatar_url = result[1] if result else None
    
    # Extract Facebook ID from Matrix user ID (e.g., @meta_123456:domain -> 123456)
    fb_profile_url = None
    if localpart.startswith("meta_"):
        fb_id = localpart.replace("meta_", "")
        if fb_id.isdigit():
            fb_profile_url = f"https://www.facebook.com/{fb_id}"
    
    return display_name, avatar_url, fb_profile_url


def backfill_archive(synapse_db, archive_db, messages):
    """Insert messages into archive database."""
    
    # Track created rooms and people
    rooms_cache = {}
    people_cache = {}
    events_cache = {}
    
    inserted = 0
    skipped = 0
    
    for msg in messages:
        # Check if already exists
        existing = archive_db.execute(
            text("SELECT id FROM messages WHERE matrix_event_id = :event_id"),
            {"event_id": msg["event_id"]}
        ).fetchone()
        
        if existing:
            events_cache[msg["event_id"]] = existing[0]
            skipped += 1
            continue
        
        # Get or create room
        if msg["room_id"] not in rooms_cache:
            room_result = archive_db.execute(
                text("SELECT id FROM rooms WHERE matrix_room_id = :room_id"),
                {"room_id": msg["room_id"]}
            ).fetchone()
            
            if room_result:
                rooms_cache[msg["room_id"]] = room_result[0]
            else:
                room_result = archive_db.execute(
                    text("""
                        INSERT INTO rooms (matrix_room_id, name, is_group)
                        VALUES (:room_id, :name, TRUE)
                        RETURNING id
                    """),
                    {"room_id": msg["room_id"], "name": msg["room_name"]}
                )
                archive_db.commit()
                rooms_cache[msg["room_id"]] = room_result.fetchone()[0]
        
        room_db_id = rooms_cache[msg["room_id"]]
        
        # Get or create person
        if msg["sender"] not in people_cache:
            person_result = archive_db.execute(
                text("SELECT id FROM people WHERE matrix_user_id = :user_id"),
                {"user_id": msg["sender"]}
            ).fetchone()
            
            if person_result:
                people_cache[msg["sender"]] = person_result[0]
            else:
                display_name, avatar_url, fb_profile_url = get_sender_profile(synapse_db, msg["sender"])
                person_result = archive_db.execute(
                    text("""
                        INSERT INTO people (matrix_user_id, display_name, avatar_url, fb_profile_url)
                        VALUES (:user_id, :display_name, :avatar_url, :fb_profile_url)
                        RETURNING id
                    """),
                    {
                        "user_id": msg["sender"], 
                        "display_name": display_name,
                        "avatar_url": avatar_url,
                        "fb_profile_url": fb_profile_url
                    }
                )
                archive_db.commit()
                people_cache[msg["sender"]] = person_result.fetchone()[0]
        
        sender_db_id = people_cache[msg["sender"]]
        
        # Get reply_to_message_id if applicable
        reply_to_msg_id = None
        if msg["reply_to_event_id"] and msg["reply_to_event_id"] in events_cache:
            reply_to_msg_id = events_cache[msg["reply_to_event_id"]]
        
        # Insert message
        result = archive_db.execute(
            text("""
                INSERT INTO messages (matrix_event_id, room_id, sender_id, content, timestamp, reply_to_message_id)
                VALUES (:event_id, :room_id, :sender_id, :content, :timestamp, :reply_to_id)
                RETURNING id
            """),
            {
                "event_id": msg["event_id"],
                "room_id": room_db_id,
                "sender_id": sender_db_id,
                "content": msg["content"],
                "timestamp": msg["timestamp"],
                "reply_to_id": reply_to_msg_id
            }
        )
        archive_db.commit()
        
        msg_id = result.fetchone()[0]
        events_cache[msg["event_id"]] = msg_id
        inserted += 1
        
        if inserted % 100 == 0:
            print(f"  Inserted {inserted} messages...")
    
    return inserted, skipped


def main():
    parser = argparse.ArgumentParser(description="Backfill archive database from Synapse")
    parser.add_argument("--room-filter", type=str, help="Filter rooms by name (partial match)")
    parser.add_argument("--limit", type=int, default=10000, help="Max messages per room")
    args = parser.parse_args()
    
    print("Connecting to databases...")
    
    synapse_engine = create_engine(SYNAPSE_DB_URL)
    archive_engine = create_engine(ARCHIVE_DB_URL)
    
    SynapseSession = sessionmaker(bind=synapse_engine)
    ArchiveSession = sessionmaker(bind=archive_engine)
    
    synapse_db = SynapseSession()
    archive_db = ArchiveSession()
    
    try:
        print(f"Fetching messages from Synapse (filter: {args.room_filter or 'all'})...")
        messages = get_synapse_messages(synapse_db, args.room_filter, args.limit)
        
        if not messages:
            print("No messages found to backfill.")
            return
        
        print(f"Found {len(messages)} messages to backfill")
        print("Inserting into archive database...")
        
        inserted, skipped = backfill_archive(synapse_db, archive_db, messages)
        
        print(f"\nBackfill complete!")
        print(f"  Inserted: {inserted}")
        print(f"  Skipped (already exist): {skipped}")
        
    finally:
        synapse_db.close()
        archive_db.close()


if __name__ == "__main__":
    main()
