"""
Archive Service - Listens to Matrix events and stores messages to PostgreSQL.

This service connects to the Dendrite homeserver, listens for messages
from bridged Messenger rooms, and archives them with sender and reply info.

Auto-links people imported from Facebook export when they become active via
the Matrix bridge, updating their records with matrix_user_id, avatar_url,
and fb_profile_url.
"""

import asyncio
import logging
import unicodedata
from datetime import datetime, timezone
from typing import Optional

import httpx
from nio import AsyncClient, MatrixRoom, RoomMessageText, RoomMessageImage, RoomMessageFile, RoomMessageAudio, RoomMessageVideo, Event
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from .config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

# Database setup
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine)


def normalize_name(name: str) -> str:
    """Normalize a name for matching purposes."""
    if not name:
        return ""
    name = unicodedata.normalize('NFC', name)
    name = name.lower().strip()
    name = ' '.join(name.split())
    return name


def extract_fb_profile_url(matrix_user_id: str) -> Optional[str]:
    """Extract Facebook profile URL from Matrix user ID."""
    # Format: @meta_123456:domain -> https://www.facebook.com/123456
    if not matrix_user_id:
        return None
    localpart = matrix_user_id.split(":")[0].lstrip("@") if ":" in matrix_user_id else matrix_user_id
    if localpart.startswith("meta_"):
        fb_id = localpart.replace("meta_", "")
        if fb_id.isdigit():
            return f"https://www.facebook.com/{fb_id}"
    return None


async def get_or_create_person(db, matrix_user_id: str, display_name: Optional[str] = None, avatar_url: Optional[str] = None):
    """
    Get or create a person record.
    
    If a person with this matrix_user_id already exists, return their ID.
    
    If not, try to match by display name to link with FB-imported people.
    This handles the case where someone was imported from Facebook export
    and later becomes active via the Matrix bridge.
    """
    # First, check if this exact matrix_user_id exists
    result = db.execute(
        text("SELECT id FROM people WHERE matrix_user_id = :user_id"),
        {"user_id": matrix_user_id}
    ).fetchone()
    
    if result:
        person_id = result[0]
        # Update display_name if we have a real one and current is missing/placeholder
        # Also update avatar_url if we have a new one
        if display_name and not display_name.startswith("meta_"):
            db.execute(
                text("""
                    UPDATE people 
                    SET display_name = COALESCE(NULLIF(:display_name, ''), display_name),
                        avatar_url = COALESCE(NULLIF(:avatar_url, ''), avatar_url)
                    WHERE id = :id 
                    AND (display_name IS NULL OR display_name LIKE 'meta_%' OR display_name = '')
                """),
                {"display_name": display_name, "avatar_url": avatar_url, "id": person_id}
            )
            db.commit()
        elif avatar_url:
            db.execute(
                text("UPDATE people SET avatar_url = :avatar_url WHERE id = :id AND (avatar_url IS NULL OR avatar_url = '')"),
                {"avatar_url": avatar_url, "id": person_id}
            )
            db.commit()
        return person_id
    
    # Try to find a matching FB-imported person by display name
    # FB imports have matrix_user_id like '@fb_import_xxx:archive.local'
    fb_profile_url = extract_fb_profile_url(matrix_user_id)
    
    if display_name:
        norm_name = normalize_name(display_name)
        
        # Look for FB-imported people with matching name
        match_result = db.execute(
            text("""
                SELECT id, display_name, fb_name 
                FROM people 
                WHERE matrix_user_id LIKE '@fb_import_%'
                AND (
                    LOWER(TRIM(display_name)) = :norm_name
                    OR LOWER(TRIM(fb_name)) = :norm_name
                )
                LIMIT 1
            """),
            {"norm_name": norm_name}
        ).fetchone()
        
        if match_result:
            person_id = match_result[0]
            logger.info(f"Auto-linking FB-imported person '{match_result[1]}' to Matrix user {matrix_user_id}")
            
            # Update the FB-imported person with real Matrix info
            db.execute(
                text("""
                    UPDATE people 
                    SET matrix_user_id = :matrix_user_id,
                        avatar_url = COALESCE(:avatar_url, avatar_url),
                        fb_profile_url = COALESCE(:fb_profile_url, fb_profile_url)
                    WHERE id = :id
                """),
                {
                    "matrix_user_id": matrix_user_id,
                    "avatar_url": avatar_url,
                    "fb_profile_url": fb_profile_url,
                    "id": person_id
                }
            )
            db.commit()
            return person_id
    
    # No match found, create new person
    result = db.execute(
        text("""
            INSERT INTO people (matrix_user_id, display_name, avatar_url, fb_profile_url)
            VALUES (:user_id, :display_name, :avatar_url, :fb_profile_url)
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


async def update_room_member(db, room_id: int, person_id: int, timestamp: datetime):
    """Update room_members stats when a new message is stored."""
    db.execute(
        text("""
            INSERT INTO room_members (room_id, person_id, first_seen_at, last_seen_at, message_count)
            VALUES (:room_id, :person_id, :timestamp, :timestamp, 1)
            ON CONFLICT (room_id, person_id) DO UPDATE SET
                first_seen_at = LEAST(room_members.first_seen_at, :timestamp),
                last_seen_at = GREATEST(room_members.last_seen_at, :timestamp),
                message_count = room_members.message_count + 1
        """),
        {"room_id": room_id, "person_id": person_id, "timestamp": timestamp}
    )
    db.commit()


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
            INSERT INTO messages (matrix_event_id, room_id, sender_id, content, timestamp, reply_to_message_id, message_type, media_url)
            VALUES (:event_id, :room_id, :sender_id, :content, :timestamp, :reply_to_id, :message_type, :media_url)
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
    
    # Update room_members stats for this new message
    await update_room_member(db, room_id, sender_id, timestamp)
    
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
            # Filter by room name if configured (exact match)
            room_filters = settings.get_room_filters()
            if room_filters:
                room_name = (room.display_name or "").lower()
                if room_name not in room_filters:
                    return  # Skip this room
            
            # Get sender's avatar URL from room member info
            avatar_url = None
            if event.sender in room.users:
                avatar_url = room.users[event.sender].avatar_url
            
            # Get or create sender (with auto-linking for FB imports)
            sender_id = await get_or_create_person(
                self.db,
                event.sender,
                room.user_name(event.sender),
                avatar_url
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
            
            # Store message (use UTC to be consistent)
            timestamp = datetime.fromtimestamp(event.server_timestamp / 1000, tz=timezone.utc)
            message_id = await store_message(
                self.db,
                event.event_id,
                room_id,
                sender_id,
                event.body,
                timestamp,
                reply_to_event_id
            )
            
            logger.info(f"Archived message from {event.sender} in {room.display_name}")
            
            # Embed message for semantic search (fire and forget)
            if message_id:
                asyncio.create_task(self._embed_message(message_id))
            
        except Exception as e:
            logger.error(f"Error archiving message: {e}")
    
    async def media_callback(self, room: MatrixRoom, event):
        """Handle incoming media messages (images, files, audio, video)."""
        try:
            # Filter by room name if configured
            room_filters = settings.get_room_filters()
            if room_filters:
                room_name = (room.display_name or "").lower()
                if room_name not in room_filters:
                    return
            
            # Determine message type based on event class
            event_type = type(event).__name__
            if event_type == "RoomMessageImage":
                message_type = "image"
            elif event_type == "RoomMessageVideo":
                message_type = "video"
            elif event_type == "RoomMessageAudio":
                message_type = "audio"
            else:
                message_type = "file"
            
            # Get media URL
            media_url = getattr(event, 'url', None)
            
            # Get sender's avatar URL
            avatar_url = None
            if event.sender in room.users:
                avatar_url = room.users[event.sender].avatar_url
            
            # Get or create sender
            sender_id = await get_or_create_person(
                self.db,
                event.sender,
                room.user_name(event.sender),
                avatar_url
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
            
            # Use body (filename or caption) as content
            content = getattr(event, 'body', None) or f"[{message_type}]"
            
            # Store message
            timestamp = datetime.fromtimestamp(event.server_timestamp / 1000, tz=timezone.utc)
            message_id = await store_message(
                self.db,
                event.event_id,
                room_id,
                sender_id,
                content,
                timestamp,
                reply_to_event_id,
                message_type=message_type,
                media_url=media_url
            )
            
            logger.info(f"Archived {message_type} from {event.sender} in {room.display_name}")
            
            # Queue image for description processing (if it's an image)
            if message_id and message_type == "image" and media_url:
                asyncio.create_task(self._queue_image_for_processing(message_id, media_url))
            
        except Exception as e:
            logger.error(f"Error archiving media message: {e}")
    
    async def _queue_image_for_processing(self, message_id: int, media_url: str):
        """Queue an image for AI description processing and trigger processing."""
        try:
            # Extract media_id from mxc:// URL
            # Format: mxc://server/media_id
            if not media_url or not media_url.startswith("mxc://"):
                return
            
            parts = media_url.replace("mxc://", "").split("/")
            if len(parts) < 2:
                return
            
            media_id = parts[1]
            
            # Create placeholder record in image_descriptions
            self.db.execute(
                text("""
                    INSERT INTO image_descriptions (message_id, media_id)
                    VALUES (:message_id, :media_id)
                    ON CONFLICT (message_id) DO NOTHING
                """),
                {"message_id": message_id, "media_id": media_id}
            )
            self.db.commit()
            logger.debug(f"Queued image {media_id} for processing")
            
            # Trigger immediate processing via API
            asyncio.create_task(self._process_image(message_id))
            
        except Exception as e:
            logger.debug(f"Could not queue image for processing: {e}")
    
    async def _process_image(self, message_id: int):
        """Trigger image processing via API. Non-blocking, logs errors."""
        try:
            api_url = settings.api_url or "http://api:8000"
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{api_url}/api/settings/images/process",
                    params={"limit": 1},
                    headers={"X-Internal-API-Key": "internal-archive-service-key"},
                    timeout=60.0  # Image processing can take a while
                )
                if response.status_code == 200:
                    result = response.json()
                    if result.get("processed", 0) > 0:
                        logger.info(f"Processed image for message {message_id}")
                elif response.status_code == 503:
                    # Service not initialized (no Gemini API key), skip silently
                    pass
                else:
                    logger.warning(f"Failed to process image {message_id}: {response.status_code}")
        except Exception as e:
            logger.debug(f"Could not process image: {e}")
    
    async def _embed_message(self, message_id: int):
        """Embed a message for semantic search. Non-blocking, logs errors."""
        try:
            api_url = settings.api_url or "http://api:8000"
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{api_url}/api/search/embed",
                    params={"entity_type": "message", "entity_id": message_id},
                    headers={"X-Internal-API-Key": "internal-archive-service-key"},
                    timeout=30.0
                )
                if response.status_code == 200:
                    logger.debug(f"Embedded message {message_id}")
                elif response.status_code == 503:
                    # Embedding service not initialized, skip silently
                    pass
                else:
                    logger.warning(f"Failed to embed message {message_id}: {response.status_code}")
        except Exception as e:
            logger.debug(f"Could not embed message {message_id}: {e}")
    
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
        
        # Register callbacks
        self.client.add_event_callback(self.message_callback, RoomMessageText)
        self.client.add_event_callback(self.media_callback, RoomMessageImage)
        self.client.add_event_callback(self.media_callback, RoomMessageVideo)
        self.client.add_event_callback(self.media_callback, RoomMessageAudio)
        self.client.add_event_callback(self.media_callback, RoomMessageFile)
        
        # Sync forever
        logger.info("Starting sync loop...")
        await self.client.sync_forever(timeout=30000)


async def main():
    """Main entry point."""
    client = ArchiveClient()
    await client.run()


if __name__ == "__main__":
    asyncio.run(main())
