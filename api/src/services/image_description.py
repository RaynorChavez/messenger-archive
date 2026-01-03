"""
Image Description Service - AI-powered image description using Gemini Vision.

Processes images through Gemini to generate descriptions and extract text (OCR).
"""

import os
import io
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

from google import genai
from google.genai import types
from sqlalchemy.orm import Session
from PIL import Image

from ..db import ImageDescription, Message

logger = logging.getLogger(__name__)

# Synapse media store path
MEDIA_STORE_PATH = os.environ.get("SYNAPSE_MEDIA_STORE", "/synapse-media")

# Max image size for LLM (in bytes) - resize if larger
MAX_IMAGE_SIZE = 500 * 1024  # 500KB
MAX_IMAGE_DIMENSION = 1024  # Max width or height

# Gemini model (same as elsewhere in the project)
MODEL = "gemini-3-flash-preview"

DESCRIPTION_PROMPT = """Analyze this image from a group chat. Provide:

1. DESCRIPTION: A detailed visual description of the image. Include:
   - What type of image it is (photo, meme, screenshot, diagram, artwork, etc.)
   - Key visual elements, colors, people, objects, or scenes shown
   - For memes: describe the template/format and the joke
   - For screenshots: describe what app/website and the key content shown
   - Do NOT start with "This image is..." - just describe what you see

2. OCR_TEXT: Transcribe ALL visible text in the image exactly as written. Include:
   - All chat messages, captions, labels, watermarks, usernames
   - Preserve line breaks and formatting where meaningful
   - If no text is visible, return empty string

Be specific and descriptive. This description will be used to search and understand the image later."""

# JSON schema for structured output
IMAGE_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {
            "type": "string",
            "description": "Detailed visual description of the image content, style, and elements"
        },
        "ocr_text": {
            "type": "string",
            "description": "Complete transcription of ALL visible text in the image. Empty string if no text."
        }
    },
    "required": ["description", "ocr_text"]
}


def get_media_path(media_id: str) -> Path:
    """Get the filesystem path for a media file based on Synapse's storage scheme.
    
    Synapse stores files at: local_content/{first2}/{next2}/{rest}
    Note: Directory names preserve original case from media_id.
    """
    if len(media_id) < 4:
        return None
    
    dir1 = media_id[:2]
    dir2 = media_id[2:4]
    filename = media_id[4:]
    
    return Path(MEDIA_STORE_PATH) / "local_content" / dir1 / dir2 / filename


def get_media_mimetype(file_path: Path) -> Optional[str]:
    """Detect mimetype from file header."""
    try:
        with open(file_path, 'rb') as f:
            header = f.read(16)
            if header.startswith(b'\xff\xd8\xff'):
                return 'image/jpeg'
            elif header.startswith(b'\x89PNG'):
                return 'image/png'
            elif header.startswith(b'GIF'):
                return 'image/gif'
            elif header.startswith(b'RIFF') and b'WEBP' in header:
                return 'image/webp'
    except Exception:
        pass
    return None


def resize_image_if_needed(image_bytes: bytes, max_size: int = MAX_IMAGE_SIZE, max_dim: int = MAX_IMAGE_DIMENSION) -> tuple[bytes, str]:
    """
    Resize image if it exceeds size limits.
    
    Returns:
        Tuple of (image_bytes, mimetype)
    """
    # Check if resize is needed
    if len(image_bytes) <= max_size:
        # Still check dimensions
        try:
            img = Image.open(io.BytesIO(image_bytes))
            if img.width <= max_dim and img.height <= max_dim:
                # Determine mimetype from format
                fmt = img.format or 'JPEG'
                mimetype = f'image/{fmt.lower()}'
                if fmt == 'JPEG':
                    mimetype = 'image/jpeg'
                return image_bytes, mimetype
        except Exception:
            pass
    
    try:
        img = Image.open(io.BytesIO(image_bytes))
        original_format = img.format or 'JPEG'
        
        # Convert to RGB if necessary (for PNG with transparency, etc.)
        if img.mode in ('RGBA', 'P', 'LA'):
            # Create white background for transparent images
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Resize if dimensions exceed max
        if img.width > max_dim or img.height > max_dim:
            ratio = min(max_dim / img.width, max_dim / img.height)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            logger.info(f"Resized image from {img.width}x{img.height} to {new_size[0]}x{new_size[1]}")
        
        # Save to bytes with quality adjustment to meet size limit
        quality = 85
        while quality >= 20:
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=quality, optimize=True)
            result_bytes = buffer.getvalue()
            
            if len(result_bytes) <= max_size:
                logger.info(f"Compressed image from {len(image_bytes)} to {len(result_bytes)} bytes (quality={quality})")
                return result_bytes, 'image/jpeg'
            
            quality -= 10
        
        # If still too large, return what we have
        logger.warning(f"Could not compress image below {max_size} bytes, using {len(result_bytes)} bytes")
        return result_bytes, 'image/jpeg'
        
    except Exception as e:
        logger.error(f"Error resizing image: {e}")
        # Return original if resize fails
        return image_bytes, 'image/jpeg'


class ImageDescriptionService:
    """Service for generating AI descriptions of images."""
    
    def __init__(self, api_key: str):
        """Initialize the service with Gemini API key."""
        self.client = genai.Client(api_key=api_key)
    
    def process_image(self, db: Session, image_desc: ImageDescription) -> bool:
        """
        Process an image and generate description.
        
        Args:
            db: Database session
            image_desc: ImageDescription record to process
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get file path
            media_path = get_media_path(image_desc.media_id)
            if not media_path or not media_path.exists():
                image_desc.error = f"Media file not found: {image_desc.media_id}"
                image_desc.processed_at = datetime.now(timezone.utc)
                db.commit()
                logger.warning(f"Media file not found: {image_desc.media_id}")
                return False
            
            # Read image bytes
            with open(media_path, 'rb') as f:
                image_bytes = f.read()
            
            original_size = len(image_bytes)
            
            # Resize if needed (also returns mimetype)
            image_bytes, mimetype = resize_image_if_needed(image_bytes)
            
            if original_size != len(image_bytes):
                logger.info(f"Resized image from {original_size} to {len(image_bytes)} bytes")
            
            # Call Gemini Vision with JSON schema
            response = self.client.models.generate_content(
                model=MODEL,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mimetype),
                    DESCRIPTION_PROMPT
                ],
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=2048,
                    response_mime_type="application/json",
                    response_schema=IMAGE_RESPONSE_SCHEMA
                )
            )
            
            # Parse JSON response
            if response.text:
                result = json.loads(response.text)
                description = result.get("description", "").strip()
                ocr_text = result.get("ocr_text", "").strip()
                
                # Treat empty ocr_text as None
                if not ocr_text:
                    ocr_text = None
                
                image_desc.description = description
                image_desc.ocr_text = ocr_text
                image_desc.processed_at = datetime.now(timezone.utc)
                image_desc.error = None
                db.commit()
                
                logger.info(f"Processed image {image_desc.media_id}: {description[:50] if description else 'no description'}...")
                return True
            else:
                image_desc.error = "Empty response from Gemini"
                image_desc.processed_at = datetime.now(timezone.utc)
                db.commit()
                return False
                
        except Exception as e:
            logger.error(f"Error processing image {image_desc.media_id}: {e}")
            image_desc.error = str(e)[:500]
            image_desc.processed_at = datetime.now(timezone.utc)
            db.commit()
            return False
    
    def process_pending_images(self, db: Session, limit: int = 10) -> int:
        """
        Process pending images that haven't been analyzed yet.
        
        Args:
            db: Database session
            limit: Maximum number of images to process
            
        Returns:
            Number of images processed
        """
        # Get unprocessed images
        pending = db.query(ImageDescription).filter(
            ImageDescription.processed_at.is_(None),
            ImageDescription.error.is_(None)
        ).limit(limit).all()
        
        processed = 0
        for image_desc in pending:
            if self.process_image(db, image_desc):
                processed += 1
        
        return processed
    
    def get_description_for_message(self, db: Session, message_id: int) -> Optional[ImageDescription]:
        """Get image description for a message, processing if needed."""
        image_desc = db.query(ImageDescription).filter(
            ImageDescription.message_id == message_id
        ).first()
        
        if not image_desc:
            return None
        
        # Process if not yet done
        if not image_desc.processed_at and not image_desc.error:
            self.process_image(db, image_desc)
        
        return image_desc


# Singleton instance
_image_service: Optional[ImageDescriptionService] = None


def get_image_description_service() -> Optional[ImageDescriptionService]:
    """Get the image description service singleton."""
    return _image_service


def init_image_description_service(api_key: str):
    """Initialize the image description service singleton."""
    global _image_service
    _image_service = ImageDescriptionService(api_key)
    logger.info("Image description service initialized")
