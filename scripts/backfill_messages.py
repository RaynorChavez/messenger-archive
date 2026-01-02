#!/usr/bin/env python3
"""
Backfill messages from Matrix/Synapse rooms to the archive database.

This script fetches historical messages from Matrix rooms and stores them
in the archive database. It handles pagination and skips duplicates.

Usage:
    docker compose exec archive-service python /app/scripts/backfill_messages.py
    
Or run directly:
    python scripts/backfill_messages.py
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nio import (
    AsyncClient,
    RoomMessagesResponse,
    RoomMessagesError,
    RoomMessageImage,
    RoomMessageVideo,
    RoomMessageAudio,
    RoomMessageFile,
)
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


# Configuration from environment
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://archive:archivepass123@localhost:5432/messenger_archive")
MATRIX_HOMESERVER = os.environ.get("MATRIX_HOMESERVER_URL", "http://localhost:8008")
MATRIX_USER_ID = os.environ.get("MATRIX_USER_ID", "@archive:archive.local")
MATRIX_PASSWORD = os.environ.get("MATRIX_PASSWORD", "archivepass123")
ROOM_FILTER = os.environ.get("ARCHIVE_ROOM_FILTER", "")

# Database setup
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def get_room_filters():
    """Parse room filter from environment."""
    if not ROOM_FILTER:
        return None
    filters = [f.strip().lower() for f in ROOM_FILTER.split(",") if f.strip()]
    return filters if filters else None


async def get_or_create_person(db, matrix_user_id: str, display_name: Optional[str] = None, avatar_url: Optional[str] = None):
    """Get or create a person record."""
    result = db.execute(
        text("SELECT id FROM people WHERE matrix_user_id = :user_id"),
        {"user_id": matrix_user_id}
    ).fetchone()
    
    if result:
        return result[0]
    
    # Extract FB profile URL
    fb_profile_url = None
    localpart = matrix_user_id.split(":")[0].lstrip("@") if ":" in matrix_user_id else matrix_user_id
    if localpart.startswith("meta_"):
        fb_id = localpart.replace("meta_", "")
        if fb_id.isdigit():
            fb_profile_url = f"https://www.facebook.com/{fb_id}"
    
    result = db.execute(
        text("""
            INSERT INTO people (matrix_user_id, display_name, avatar_url, fb_profile_url)
            VALUES (:user_id, :display_name, :avatar_url, :fb_profile_url)
            ON CONFLICT (matrix_user_id) DO UPDATE SET 
                display_name = COALESCE(EXCLUDED.display_name, people.display_name),
                avatar_url = COALESCE(EXCLUDED.avatar_url, people.avatar_url)
            RETURNING id
        """),
        {
            "user_id": matrix_user_id,
            "display_name": display_name,
            "avatar_url": avatar_url,
            "fb_profile_url": fb_profile_url
        }
    )
    db.commit()
    return result.fetchone()[0]


async def get_or_create_room(db, matrix_room_id: str, name: Optional[str] = None):
    """Get or create a room record."""
    result = db.execute(
        text("SELECT id FROM rooms WHERE matrix_room_id = :room_id"),
        {"room_id": matrix_room_id}
    ).fetchone()
    
    if result:
        return result[0]
    
    # Get max display_order
    max_order = db.execute(text("SELECT COALESCE(MAX(display_order), 0) FROM rooms")).fetchone()[0]
    
    result = db.execute(
        text("""
            INSERT INTO rooms (matrix_room_id, name, is_group, display_order)
            VALUES (:room_id, :name, TRUE, :display_order)
            RETURNING id
        """),
        {"room_id": matrix_room_id, "name": name, "display_order": max_order + 1}
    )
    db.commit()
    return result.fetchone()[0]


async def message_exists(db, matrix_event_id: str) -> bool:
    """Check if a message already exists."""
    result = db.execute(
        text("SELECT 1 FROM messages WHERE matrix_event_id = :event_id"),
        {"event_id": matrix_event_id}
    ).fetchone()
    return result is not None


async def get_message_id_by_event(db, matrix_event_id: str) -> Optional[int]:
    """Get message ID by Matrix event ID."""
    result = db.execute(
        text("SELECT id FROM messages WHERE matrix_event_id = :event_id"),
        {"event_id": matrix_event_id}
    ).fetchone()
    return result[0] if result else None


async def store_message(
    db,
    matrix_event_id: str,
    room_id: int,
    sender_id: int,
    content: str,
    timestamp: datetime,
    reply_to_event_id: Optional[str] = None,
    message_type: str = "text",
    media_url: Optional[str] = None
) -> Optional[int]:
    """Store a message in the database."""
    # Check if already exists
    if await message_exists(db, matrix_event_id):
        return None
    
    # Get reply_to_message_id if this is a reply
    reply_to_message_id = None
    if reply_to_event_id:
        reply_to_message_id = await get_message_id_by_event(db, reply_to_event_id)
    
    result = db.execute(
        text("""
            INSERT INTO messages (matrix_event_id, room_id, sender_id, content, timestamp, reply_to_message_id, message_type, media_url)
            VALUES (:event_id, :room_id, :sender_id, :content, :timestamp, :reply_to_id, :message_type, :media_url)
            ON CONFLICT (matrix_event_id) DO NOTHING
            RETURNING id
        """),
        {
            "event_id": matrix_event_id,
            "room_id": room_id,
            "sender_id": sender_id,
            "content": content,
            "timestamp": timestamp,
            "reply_to_id": reply_to_message_id,
            "message_type": message_type,
            "media_url": media_url
        }
    )
    db.commit()
    row = result.fetchone()
    return row[0] if row else None


async def queue_image_for_processing(db, message_id: int, media_url: str):
    """Queue an image for later processing by creating an image_descriptions record."""
    # Extract media_id from mxc:// URL
    # Format: mxc://server/media_id
    if not media_url or not media_url.startswith("mxc://"):
        return
    
    parts = media_url.split("/")
    if len(parts) < 4:
        return
    
    media_id = parts[-1]
    
    db.execute(
        text("""
            INSERT INTO image_descriptions (message_id, media_id)
            VALUES (:message_id, :media_id)
            ON CONFLICT (media_id) DO NOTHING
        """),
        {"message_id": message_id, "media_id": media_id}
    )
    db.commit()


async def backfill_room(client: AsyncClient, db, room_id: str, room_name: str, limit: int = 10000):
    """Backfill messages from a single room."""
    print(f"\nBackfilling room: {room_name} ({room_id})")
    
    # Get or create room in DB
    db_room_id = await get_or_create_room(db, room_id, room_name)
    
    messages_added = 0
    messages_skipped = 0
    batch_count = 0
    
    # Start from the beginning (empty string = start from now, going backwards)
    from_token = ""
    
    while True:
        batch_count += 1
        
        # Fetch messages
        response = await client.room_messages(
            room_id,
            start=from_token,
            limit=100,
            direction="b"  # backwards
        )
        
        if isinstance(response, RoomMessagesError):
            print(f"  Error fetching messages: {response.message}")
            break
        
        if not response.chunk:
            print(f"  No more messages to fetch")
            break
        
        for event in response.chunk:
            # Determine message type and content
            event_class = event.__class__.__name__
            message_type = "text"
            content = ""
            media_url = None
            
            if event_class == "RoomMessageText":
                message_type = "text"
                content = event.body
            elif event_class == "RoomMessageImage":
                message_type = "image"
                content = getattr(event, 'body', '[Image]')
                media_url = getattr(event, 'url', None)
            elif event_class == "RoomMessageVideo":
                message_type = "video"
                content = getattr(event, 'body', '[Video]')
                media_url = getattr(event, 'url', None)
            elif event_class == "RoomMessageAudio":
                message_type = "audio"
                content = getattr(event, 'body', '[Audio]')
                media_url = getattr(event, 'url', None)
            elif event_class == "RoomMessageFile":
                message_type = "file"
                content = getattr(event, 'body', '[File]')
                media_url = getattr(event, 'url', None)
            else:
                # Skip other event types (state events, reactions, etc.)
                continue
            
            # Get sender info
            sender_name = None
            avatar_url = None
            if hasattr(event, 'sender') and event.sender:
                # Try to get display name from room state
                sender_name = event.sender.split(":")[0].lstrip("@")
                if sender_name.startswith("meta_"):
                    sender_name = sender_name.replace("meta_", "")
            
            sender_id = await get_or_create_person(db, event.sender, sender_name, avatar_url)
            
            # Check for reply
            reply_to_event_id = None
            if hasattr(event, 'source') and event.source:
                relates_to = event.source.get('content', {}).get('m.relates_to', {})
                if relates_to.get('m.in_reply_to'):
                    reply_to_event_id = relates_to['m.in_reply_to'].get('event_id')
            
            # Convert timestamp
            timestamp = datetime.fromtimestamp(event.server_timestamp / 1000, tz=timezone.utc)
            
            # Store message
            msg_id = await store_message(
                db,
                event.event_id,
                db_room_id,
                sender_id,
                content,
                timestamp,
                reply_to_event_id,
                message_type,
                media_url
            )
            
            if msg_id:
                messages_added += 1
                # Queue image for processing
                if message_type == "image" and media_url:
                    await queue_image_for_processing(db, msg_id, media_url)
            else:
                messages_skipped += 1
        
        print(f"  Batch {batch_count}: +{messages_added} new, {messages_skipped} skipped", end="\r")
        
        # Check if we've hit the limit
        if messages_added + messages_skipped >= limit:
            print(f"\n  Reached limit of {limit} messages")
            break
        
        # Move to next batch
        if response.end:
            from_token = response.end
        else:
            break
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(0.1)
    
    print(f"\n  Done: {messages_added} messages added, {messages_skipped} already existed")
    return messages_added


async def main():
    """Main backfill function."""
    print("=" * 60)
    print("Matrix Message Backfill Script")
    print("=" * 60)
    
    db = SessionLocal()
    
    # Create Matrix client
    client = AsyncClient(MATRIX_HOMESERVER, MATRIX_USER_ID)
    
    print(f"\nConnecting to {MATRIX_HOMESERVER} as {MATRIX_USER_ID}...")
    
    # Login
    response = await client.login(MATRIX_PASSWORD)
    if hasattr(response, 'access_token'):
        print("Logged in successfully")
    else:
        print(f"Login failed: {response}")
        return
    
    # Get list of joined rooms
    rooms_response = await client.joined_rooms()
    if hasattr(rooms_response, 'rooms'):
        print(f"\nFound {len(rooms_response.rooms)} joined rooms")
    else:
        print(f"Failed to get rooms: {rooms_response}")
        return
    
    room_filters = get_room_filters()
    if room_filters:
        print(f"Filtering to rooms: {room_filters}")
    
    total_added = 0
    
    # Process each room
    for room_id in rooms_response.rooms:
        # Get room info
        room = client.rooms.get(room_id)
        room_name = room.display_name if room else room_id
        
        # Apply filter
        if room_filters:
            if room_name.lower() not in room_filters:
                print(f"\nSkipping room: {room_name} (not in filter)")
                continue
        
        added = await backfill_room(client, db, room_id, room_name)
        total_added += added
    
    print(f"\n{'=' * 60}")
    print(f"Backfill complete! Total messages added: {total_added}")
    print("=" * 60)
    
    # Update room_members table
    print("\nUpdating room_members table...")
    db.execute(text("""
        INSERT INTO room_members (room_id, person_id, first_seen_at, last_seen_at, message_count)
        SELECT 
            m.room_id,
            m.sender_id,
            MIN(m.timestamp),
            MAX(m.timestamp),
            COUNT(*)
        FROM messages m
        WHERE m.sender_id IS NOT NULL
        GROUP BY m.room_id, m.sender_id
        ON CONFLICT (room_id, person_id) DO UPDATE SET
            first_seen_at = LEAST(room_members.first_seen_at, EXCLUDED.first_seen_at),
            last_seen_at = GREATEST(room_members.last_seen_at, EXCLUDED.last_seen_at),
            message_count = EXCLUDED.message_count
    """))
    db.commit()
    print("Done!")
    
    # Close connections
    await client.close()
    db.close()


if __name__ == "__main__":
    asyncio.run(main())
