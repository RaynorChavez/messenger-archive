"""Media proxy router - serves Matrix media files directly from disk."""

import os
import mimetypes
from pathlib import Path
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse

router = APIRouter(prefix="/media", tags=["media"])

# Synapse media store path (mounted in the container)
MEDIA_STORE_PATH = os.environ.get("SYNAPSE_MEDIA_STORE", "/synapse-media")


def get_media_path(media_id: str) -> Path:
    """Get the filesystem path for a media file based on Synapse's storage scheme.
    
    Synapse stores files at: local_content/{first2_lowercase}/{next2_lowercase}/{rest}
    """
    if len(media_id) < 4:
        raise HTTPException(status_code=400, detail="Invalid media ID")
    
    # Synapse uses lowercase for first 4 chars in path
    dir1 = media_id[:2].lower()
    dir2 = media_id[2:4].lower()
    filename = media_id[4:]
    
    return Path(MEDIA_STORE_PATH) / "local_content" / dir1 / dir2 / filename


@router.get("/{server_name}/{media_id}")
async def get_media(server_name: str, media_id: str):
    """Serve Matrix media files directly from the Synapse media store."""
    # Only serve local media
    if server_name != "archive.local":
        raise HTTPException(status_code=404, detail="Only local media is supported")
    
    media_path = get_media_path(media_id)
    
    if not media_path.exists():
        raise HTTPException(status_code=404, detail="Media not found")
    
    # Guess content type from file
    content_type, _ = mimetypes.guess_type(str(media_path))
    if not content_type:
        # Try to detect from file content
        with open(media_path, 'rb') as f:
            header = f.read(16)
            if header.startswith(b'\xff\xd8\xff'):
                content_type = 'image/jpeg'
            elif header.startswith(b'\x89PNG'):
                content_type = 'image/png'
            elif header.startswith(b'GIF'):
                content_type = 'image/gif'
            elif header.startswith(b'RIFF') and b'WEBP' in header:
                content_type = 'image/webp'
            else:
                content_type = 'application/octet-stream'
    
    return FileResponse(
        path=media_path,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=86400",  # Cache for 24 hours
        }
    )
