#!/usr/bin/env python3
"""
Import Facebook Messenger export into archive database.

This script imports messages from a Facebook data export (JSON format) into the
messenger archive database. It handles:
- Matching senders to existing people by normalized name
- Creating new people records for unmatched senders (with fb_name for later linking)
- Deduplicating messages by timestamp + sender + content hash
- Fixing Facebook's broken UTF-8 encoding

Usage:
    python scripts/import_fb_export.py /path/to/message_1.json --room-name "General Chat"
    
Or via docker:
    docker compose exec api python /app/scripts/import_fb_export.py /path/to/message_1.json
"""

import argparse
import json
import hashlib
import unicodedata
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Database URL - adjust if running outside docker
ARCHIVE_DB_URL = "postgresql://archive:archivepass123@postgres:5432/messenger_archive"


def fix_facebook_encoding(text: str) -> str:
    """
    Fix Facebook's broken UTF-8 encoding.
    
    Facebook exports encode UTF-8 strings as if they were Latin-1, resulting in
    mojibake like 'PeÃ±a' instead of 'Peña'.
    """
    if not text:
        return text
    try:
        # Encode as Latin-1 (treating each char as a byte), then decode as UTF-8
        return text.encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


def normalize_name(name: str) -> str:
    """
    Normalize a name for matching purposes.
    
    - Fixes Facebook encoding
    - Lowercases
    - Removes extra whitespace
    - Normalizes Unicode (NFC form)
    """
    if not name:
        return ""
    
    name = fix_facebook_encoding(name)
    name = unicodedata.normalize('NFC', name)
    name = name.lower().strip()
    name = ' '.join(name.split())  # Normalize whitespace
    return name


def content_hash(sender: str, timestamp_ms: int, content: str) -> str:
    """Generate a hash for deduplication."""
    data = f"{sender}|{timestamp_ms}|{content or ''}"
    return hashlib.sha256(data.encode('utf-8')).hexdigest()[:32]


def load_facebook_export(path: str) -> dict:
    """Load and parse a Facebook message export JSON file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_or_create_room(db, room_name: str) -> int:
    """Get or create a room by name (for FB imports without Matrix room ID)."""
    # First check if room exists with this name
    result = db.execute(
        text("SELECT id FROM rooms WHERE name = :name"),
        {"name": room_name}
    ).fetchone()
    
    if result:
        return result[0]
    
    # Create new room without matrix_room_id (will be linked later via bridge)
    result = db.execute(
        text("""
            INSERT INTO rooms (matrix_room_id, name, is_group)
            VALUES (:room_id, :name, TRUE)
            RETURNING id
        """),
        {"room_id": f"fb_import_{room_name[:50]}", "name": room_name}
    )
    db.commit()
    return result.fetchone()[0]


def build_people_lookup(db) -> dict:
    """
    Build a lookup table for matching people by normalized name.
    
    Returns dict mapping normalized_name -> person_id
    """
    result = db.execute(
        text("SELECT id, display_name, fb_name FROM people")
    ).fetchall()
    
    lookup = {}
    for person_id, display_name, fb_name in result:
        # Index by display_name
        if display_name:
            norm = normalize_name(display_name)
            if norm and norm not in lookup:
                lookup[norm] = person_id
        
        # Also index by fb_name if different
        if fb_name:
            norm = normalize_name(fb_name)
            if norm and norm not in lookup:
                lookup[norm] = person_id
    
    return lookup


def get_or_create_person(db, fb_name: str, people_lookup: dict) -> int:
    """
    Get existing person by name match, or create new one.
    
    For FB imports, we don't have matrix_user_id yet. We create a placeholder
    that will be linked when the user becomes active via the Matrix bridge.
    """
    norm_name = normalize_name(fb_name)
    fixed_name = fix_facebook_encoding(fb_name)
    
    # Check lookup
    if norm_name in people_lookup:
        return people_lookup[norm_name]
    
    # Check if already exists with this fb_name
    result = db.execute(
        text("SELECT id FROM people WHERE fb_name = :fb_name"),
        {"fb_name": fb_name}
    ).fetchone()
    
    if result:
        people_lookup[norm_name] = result[0]
        return result[0]
    
    # Create new person without matrix_user_id
    # Use a placeholder matrix_user_id since it's required (unique constraint)
    placeholder_id = f"@fb_import_{hashlib.md5(fb_name.encode()).hexdigest()[:12]}:archive.local"
    
    result = db.execute(
        text("""
            INSERT INTO people (matrix_user_id, display_name, fb_name)
            VALUES (:matrix_user_id, :display_name, :fb_name)
            ON CONFLICT (matrix_user_id) DO UPDATE SET fb_name = :fb_name
            RETURNING id
        """),
        {
            "matrix_user_id": placeholder_id,
            "display_name": fixed_name,
            "fb_name": fb_name
        }
    )
    db.commit()
    
    person_id = result.fetchone()[0]
    people_lookup[norm_name] = person_id
    return person_id


def get_existing_hashes(db, room_id: int) -> set:
    """Get all existing content hashes for a room to enable deduplication."""
    # We'll compute hashes for existing messages
    result = db.execute(
        text("""
            SELECT p.display_name, m.timestamp, m.content
            FROM messages m
            JOIN people p ON m.sender_id = p.id
            WHERE m.room_id = :room_id
        """),
        {"room_id": room_id}
    ).fetchall()
    
    hashes = set()
    for sender, ts, content in result:
        ts_ms = int(ts.timestamp() * 1000)
        h = content_hash(sender or "", ts_ms, content or "")
        hashes.add(h)
    
    return hashes


def import_messages(db, messages: list, room_id: int, people_lookup: dict, existing_hashes: set):
    """Import messages into the database."""
    inserted = 0
    skipped = 0
    
    # Messages are in reverse chronological order, reverse for proper insertion
    messages = list(reversed(messages))
    
    for i, msg in enumerate(messages):
        sender_name = msg.get('sender_name', 'Unknown')
        timestamp_ms = msg.get('timestamp_ms', 0)
        content = msg.get('content', '')
        
        # Fix encoding on content
        if content:
            content = fix_facebook_encoding(content)
        
        # Check for duplicates
        fixed_sender = fix_facebook_encoding(sender_name)
        h = content_hash(fixed_sender, timestamp_ms, content or "")
        if h in existing_hashes:
            skipped += 1
            continue
        
        # Get or create person
        sender_id = get_or_create_person(db, sender_name, people_lookup)
        
        # Generate a placeholder event ID for FB imports
        event_id = f"$fb_import_{h}"
        
        # Check if this event_id already exists
        existing = db.execute(
            text("SELECT id FROM messages WHERE matrix_event_id = :event_id"),
            {"event_id": event_id}
        ).fetchone()
        
        if existing:
            skipped += 1
            continue
        
        # Handle different message types
        msg_type = msg.get('type', 'Generic')
        
        # For photos, videos, etc., create a description if no content
        if not content:
            if 'photos' in msg:
                content = f"[Photo: {len(msg['photos'])} image(s)]"
            elif 'videos' in msg:
                content = f"[Video: {len(msg['videos'])} video(s)]"
            elif 'audio_files' in msg:
                content = "[Audio message]"
            elif 'gifs' in msg:
                content = "[GIF]"
            elif 'sticker' in msg:
                content = "[Sticker]"
            elif 'share' in msg:
                link = msg['share'].get('link', '')
                content = f"[Shared: {link}]" if link else "[Shared content]"
            elif 'files' in msg:
                content = f"[File: {len(msg['files'])} file(s)]"
            elif msg.get('is_unsent'):
                content = "[Message unsent]"
            else:
                content = f"[{msg_type}]"
        
        # Handle reactions - store as part of content for now
        reactions = msg.get('reactions', [])
        if reactions:
            reaction_str = ', '.join([
                f"{fix_facebook_encoding(r.get('reaction', '?'))} by {fix_facebook_encoding(r.get('actor', '?'))}"
                for r in reactions
            ])
            # Don't append to content, could add reactions table later
        
        # Insert message
        timestamp = datetime.fromtimestamp(timestamp_ms / 1000)
        
        db.execute(
            text("""
                INSERT INTO messages (matrix_event_id, room_id, sender_id, content, timestamp)
                VALUES (:event_id, :room_id, :sender_id, :content, :timestamp)
            """),
            {
                "event_id": event_id,
                "room_id": room_id,
                "sender_id": sender_id,
                "content": content,
                "timestamp": timestamp
            }
        )
        
        inserted += 1
        existing_hashes.add(h)
        
        if inserted % 500 == 0:
            db.commit()
            print(f"  Progress: {inserted} inserted, {skipped} skipped...")
    
    db.commit()
    return inserted, skipped


def main():
    parser = argparse.ArgumentParser(description="Import Facebook Messenger export")
    parser.add_argument("json_file", type=str, help="Path to message_1.json file")
    parser.add_argument("--room-name", type=str, required=True, 
                        help="Name for the room in archive database")
    parser.add_argument("--db-url", type=str, default=ARCHIVE_DB_URL,
                        help="Database URL (default: docker internal)")
    args = parser.parse_args()
    
    print(f"Loading Facebook export from {args.json_file}...")
    data = load_facebook_export(args.json_file)
    
    messages = data.get('messages', [])
    participants = data.get('participants', [])
    
    print(f"Found {len(messages)} messages from {len(participants)} participants")
    
    print(f"Connecting to database...")
    engine = create_engine(args.db_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        # Get or create room
        print(f"Setting up room: {args.room_name}")
        room_id = get_or_create_room(db, args.room_name)
        print(f"  Room ID: {room_id}")
        
        # Build people lookup
        print("Building people lookup table...")
        people_lookup = build_people_lookup(db)
        print(f"  Found {len(people_lookup)} existing people")
        
        # Get existing message hashes for deduplication
        print("Loading existing messages for deduplication...")
        existing_hashes = get_existing_hashes(db, room_id)
        print(f"  Found {len(existing_hashes)} existing messages")
        
        # Import messages
        print("Importing messages...")
        inserted, skipped = import_messages(db, messages, room_id, people_lookup, existing_hashes)
        
        print(f"\nImport complete!")
        print(f"  Inserted: {inserted}")
        print(f"  Skipped (duplicates): {skipped}")
        
        # Show people stats
        new_people = db.execute(
            text("SELECT COUNT(*) FROM people WHERE matrix_user_id LIKE '@fb_import_%'")
        ).fetchone()[0]
        print(f"  New people created: {new_people}")
        
    finally:
        db.close()


if __name__ == "__main__":
    main()
