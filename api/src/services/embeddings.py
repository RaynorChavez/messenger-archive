"""
Embedding Service - Gemini-powered vector embeddings for semantic search.

Uses Gemini's text-embedding-004 model to generate 768-dimensional embeddings
for messages, discussions, people, and topics.
"""

import hashlib
import logging
from typing import Optional, List
from dataclasses import dataclass

from google import genai

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """Result of an embedding operation."""
    text: str
    embedding: List[float]
    content_hash: str


class EmbeddingService:
    """Service for generating text embeddings using Gemini."""
    
    MODEL = "text-embedding-004"
    DIMENSIONS = 768
    BATCH_SIZE = 100  # Gemini supports up to 100 texts per batch
    
    def __init__(self, api_key: str):
        """Initialize the embedding service.
        
        Args:
            api_key: Google AI API key
        """
        self.client = genai.Client(api_key=api_key)
        logger.info(f"Embedding service initialized with model {self.MODEL}")
    
    @staticmethod
    def get_content_hash(text: str) -> str:
        """Generate SHA256 hash of text content for change detection.
        
        Args:
            text: The text to hash
            
        Returns:
            SHA256 hex digest
        """
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
    
    def embed_text(self, text: str) -> EmbeddingResult:
        """Embed a single text.
        
        Args:
            text: The text to embed
            
        Returns:
            EmbeddingResult with embedding and content hash
        """
        if not text or not text.strip():
            raise ValueError("Cannot embed empty text")
        
        # Truncate very long texts (Gemini has token limits)
        # ~4 chars per token, 2048 token limit for embeddings
        max_chars = 8000
        if len(text) > max_chars:
            text = text[:max_chars]
            logger.debug(f"Truncated text to {max_chars} chars for embedding")
        
        try:
            response = self.client.models.embed_content(
                model=self.MODEL,
                contents=text
            )
            
            if not response.embeddings or len(response.embeddings) == 0:
                raise ValueError("No embeddings returned from API")
            
            embedding_values = response.embeddings[0].values
            if embedding_values is None:
                raise ValueError("Embedding values are None")
            
            return EmbeddingResult(
                text=text,
                embedding=list(embedding_values),
                content_hash=self.get_content_hash(text)
            )
            
        except Exception as e:
            logger.error(f"Error embedding text: {e}")
            raise
    
    def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        """Embed multiple texts in one API call.
        
        Args:
            texts: List of texts to embed (max 100)
            
        Returns:
            List of EmbeddingResults in same order as input
        """
        if not texts:
            return []
        
        if len(texts) > self.BATCH_SIZE:
            raise ValueError(f"Batch size {len(texts)} exceeds maximum {self.BATCH_SIZE}")
        
        # Filter and truncate texts
        max_chars = 8000
        processed_texts = []
        valid_indices = []
        
        for i, text in enumerate(texts):
            if text and text.strip():
                if len(text) > max_chars:
                    text = text[:max_chars]
                processed_texts.append(text)
                valid_indices.append(i)
        
        if not processed_texts:
            return []
        
        try:
            response = self.client.models.embed_content(
                model=self.MODEL,
                contents=processed_texts
            )
            
            if not response.embeddings:
                raise ValueError("No embeddings returned from API")
            
            results = []
            for idx, embedding_data in enumerate(response.embeddings):
                text = processed_texts[idx]
                embedding_values = embedding_data.values
                if embedding_values is None:
                    raise ValueError(f"Embedding values are None for text {idx}")
                results.append(EmbeddingResult(
                    text=text,
                    embedding=list(embedding_values),
                    content_hash=self.get_content_hash(text)
                ))
            
            return results
            
        except Exception as e:
            logger.error(f"Error batch embedding {len(processed_texts)} texts: {e}")
            raise
    
    def prepare_message_content(self, content: str) -> str:
        """Prepare message content for embedding.
        
        Args:
            content: Raw message content
            
        Returns:
            Cleaned content suitable for embedding
        """
        if not content:
            return ""
        
        # Remove common noise patterns
        content = content.strip()
        
        # Skip very short messages (reactions, single emojis, etc.)
        if len(content) < 5:
            return ""
        
        return content
    
    def prepare_discussion_content(self, title: str, summary: Optional[str] = None) -> str:
        """Prepare discussion content for embedding.
        
        Args:
            title: Discussion title
            summary: Optional discussion summary
            
        Returns:
            Combined content suitable for embedding
        """
        parts = [title]
        if summary:
            parts.append(summary)
        return " ".join(parts)
    
    def prepare_person_content(self, display_name: str, summary: Optional[str] = None) -> str:
        """Prepare person content for embedding.
        
        Args:
            display_name: Person's display name
            summary: Optional AI-generated summary
            
        Returns:
            Combined content suitable for embedding
        """
        parts = [display_name]
        if summary:
            parts.append(summary)
        return " ".join(parts)
    
    def prepare_topic_content(self, name: str, description: Optional[str] = None) -> str:
        """Prepare topic content for embedding.
        
        Args:
            name: Topic name
            description: Optional topic description
            
        Returns:
            Combined content suitable for embedding
        """
        parts = [name]
        if description:
            parts.append(description)
        return " ".join(parts)


# Singleton instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Get the embedding service singleton.
    
    Must be initialized first by calling init_embedding_service().
    """
    global _embedding_service
    if _embedding_service is None:
        raise RuntimeError("Embedding service not initialized. Call init_embedding_service() first.")
    return _embedding_service


def init_embedding_service(api_key: str):
    """Initialize the embedding service singleton.
    
    Args:
        api_key: Google AI API key
    """
    global _embedding_service
    _embedding_service = EmbeddingService(api_key)
    logger.info("Embedding service initialized")
