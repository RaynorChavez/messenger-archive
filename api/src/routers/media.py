"""Media proxy router - proxies Matrix media requests."""

import httpx
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/media", tags=["media"])

# Matrix homeserver URL (internal Docker network)
MATRIX_MEDIA_URL = "http://synapse:8008/_matrix/media/v3/download"


@router.get("/{server_name}/{media_id}")
async def proxy_media(server_name: str, media_id: str):
    """Proxy Matrix media through the API to avoid exposing Synapse directly."""
    url = f"{MATRIX_MEDIA_URL}/{server_name}/{media_id}"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Media not found")
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to fetch media: {response.status_code}"
                )
            
            # Get content type from response
            content_type = response.headers.get("content-type", "application/octet-stream")
            
            return Response(
                content=response.content,
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",  # Cache for 24 hours
                }
            )
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Media request timed out")
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Failed to fetch media: {str(e)}")
