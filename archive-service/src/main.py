"""
Archive Service - Listens to Matrix events and stores messages to PostgreSQL.

This service connects to the Dendrite homeserver, listens for messages
from bridged Messenger rooms, and archives them with sender and reply info.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from nio import AsyncClient, MatrixRoom, RoomMessageText, Event
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from .config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

# Database setup
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine)


async def get_or_create_person(db, matrix_user_id: str, display_name: Optional[str] = None):
    """Get or create a person record."""
    result = db.execute(
        text("SELECT id FROM people WHERE matrix_user_id = :user_id"),
        {"user_id": matrix_user_id}
    ).fetchone()
    
    if result:
        return result[0]
    
    result = db.execute(
        text("""
            INSERT INTO people (matrix_user_id, display_name)
            VALUES (:user_id, :display_name)
            RETURNING id
        """),
        {"user_id": matrix_user_id, "display_name": display_name}
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
    
    result = db.execute(
        text("""
            INSERT INTO rooms (matrix_room_id, name, is_group)
            VALUES (:room_id, :name, TRUE)
            RETURNING id
        """),
        {"room_id": matrix_room_id, "name": name}
    )
    db.commit()
    return result.fetchone()[0]


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
    reply_to_event_id: Optional[str] = None
):
    """Store a message in the database."""
    # Check if already exists
    existing = await get_message_id_by_event(db, matrix_event_id)
    if existing:
        logger.debug(f"Message {matrix_event_id} already exists, skipping")
        return existing
    
    # Get reply_to_message_id if this is a reply
    reply_to_message_id = None
    if reply_to_event_id:
        reply_to_message_id = await get_message_id_by_event(db, reply_to_event_id)
    
    result = db.execute(
        text("""
            INSERT INTO messages (matrix_event_id, room_id, sender_id, content, timestamp, reply_to_message_id)
            VALUES (:event_id, :room_id, :sender_id, :content, :timestamp, :reply_to_id)
            RETURNING id
        """),
        {
            "event_id": matrix_event_id,
            "room_id": room_id,
            "sender_id": sender_id,
            "content": content,
            "timestamp": timestamp,
            "reply_to_id": reply_to_message_id
        }
    )
    db.commit()
    return result.fetchone()[0]


class ArchiveClient:
    """Matrix client that archives messages to PostgreSQL."""
    
    def __init__(self):
        self.client = AsyncClient(
            settings.matrix_homeserver_url,
            settings.matrix_user_id
        )
        self.db = SessionLocal()
    
    async def message_callback(self, room: MatrixRoom, event: RoomMessageText):
        """Handle incoming text messages."""
        try:
            # Filter by room name if configured
            if settings.archive_room_filter:
                room_name = room.display_name or ""
                if settings.archive_room_filter.lower() not in room_name.lower():
                    return  # Skip this room
            
            # Get or create sender
            sender_id = await get_or_create_person(
                self.db,
                event.sender,
                room.user_name(event.sender)
            )
            
            # Get or create room
            room_id = await get_or_create_room(
                self.db,
                room.room_id,
                room.display_name
            )
            
            # Check for reply
            reply_to_event_id = None
            if hasattr(event, 'source') and event.source:
                relates_to = event.source.get('content', {}).get('m.relates_to', {})
                if relates_to.get('m.in_reply_to'):
                    reply_to_event_id = relates_to['m.in_reply_to'].get('event_id')
            
            # Store message
            timestamp = datetime.fromtimestamp(event.server_timestamp / 1000)
            await store_message(
                self.db,
                event.event_id,
                room_id,
                sender_id,
                event.body,
                timestamp,
                reply_to_event_id
            )
            
            logger.info(f"Archived message from {event.sender} in {room.display_name}")
            
        except Exception as e:
            logger.error(f"Error archiving message: {e}")
    
    async def run(self):
        """Run the archive client."""
        logger.info("Starting archive service...")
        
        # Login
        response = await self.client.login(settings.matrix_password)
        if hasattr(response, 'access_token'):
            logger.info("Logged in successfully")
        else:
            logger.error(f"Login failed: {response}")
            return
        
        # Register callback
        self.client.add_event_callback(self.message_callback, RoomMessageText)
        
        # Sync forever
        logger.info("Starting sync loop...")
        await self.client.sync_forever(timeout=30000)


async def main():
    """Main entry point."""
    client = ArchiveClient()
    await client.run()


if __name__ == "__main__":
    asyncio.run(main())
