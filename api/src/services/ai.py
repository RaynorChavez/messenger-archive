"""
AI Service - Gemini-powered profile summary generation.

Uses the Google GenAI SDK with rate limiting to generate personality
profiles from a person's message history.
"""

import time
import logging
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


@dataclass
class TokenBucket:
    """Sliding window rate limiter for token usage."""
    
    max_tokens_per_minute: int = 800_000
    window_seconds: int = 60
    _usage: list = field(default_factory=list)  # List of (timestamp, tokens) tuples
    
    def _cleanup_old_entries(self):
        """Remove entries older than the window."""
        cutoff = time.time() - self.window_seconds
        self._usage = [(ts, tokens) for ts, tokens in self._usage if ts > cutoff]
    
    def get_current_usage(self) -> int:
        """Get current token usage in the window."""
        self._cleanup_old_entries()
        return sum(tokens for _, tokens in self._usage)
    
    def can_use(self, tokens: int) -> bool:
        """Check if we can use the specified number of tokens."""
        current = self.get_current_usage()
        return (current + tokens) <= self.max_tokens_per_minute
    
    def record_usage(self, tokens: int):
        """Record token usage."""
        self._usage.append((time.time(), tokens))
    
    def time_until_available(self, tokens: int) -> float:
        """Get seconds until the specified tokens would be available."""
        self._cleanup_old_entries()
        if not self._usage:
            return 0
        
        current = self.get_current_usage()
        if (current + tokens) <= self.max_tokens_per_minute:
            return 0
        
        # Find when enough tokens will expire
        needed = (current + tokens) - self.max_tokens_per_minute
        accumulated = 0
        for ts, tok in sorted(self._usage):
            accumulated += tok
            if accumulated >= needed:
                return max(0, (ts + self.window_seconds) - time.time())
        
        return self.window_seconds


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""
    def __init__(self, retry_after: float):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after:.1f} seconds.")


class AIService:
    """Service for AI-powered profile generation using Gemini."""
    
    MODEL = "gemini-3-flash-preview"
    THINKING_BUDGET = 712
    
    PROMPT_TEMPLATE = """Analyze the following messages from {person_name} in a philosophy discussion group called "Manila Dialectics Society". Generate a brief personality profile (2-3 paragraphs) covering:

- Communication style and tone
- Topics and themes they discuss most (philosophical or otherwise)
- Notable perspectives or recurring ideas
- Any other interesting patterns

Keep it objective and insightful. Do not use bullet points in your response - write in prose.

Note: Ignore any "[message edited]" indicators or edit history - focus only on the actual content of what they said.

Messages (with timestamps):
{messages}"""
    
    def __init__(self, api_key: str, max_tokens_per_minute: int = 800_000):
        """Initialize the AI service.
        
        Args:
            api_key: Google AI API key
            max_tokens_per_minute: Rate limit for token usage (default 800k)
        """
        self.client = genai.Client(api_key=api_key)
        self.rate_limiter = TokenBucket(max_tokens_per_minute=max_tokens_per_minute)
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (chars / 4)."""
        return len(text) // 4
    
    def _format_messages(self, messages: list[tuple[datetime, str]]) -> str:
        """Format messages with timestamps for the prompt.
        
        Args:
            messages: List of (timestamp, content) tuples
            
        Returns:
            Formatted string of messages
        """
        lines = []
        for timestamp, content in messages:
            ts_str = timestamp.strftime("%Y-%m-%d %H:%M")
            # Truncate very long messages
            if len(content) > 500:
                content = content[:500] + "..."
            lines.append(f"[{ts_str}] {content}")
        return "\n".join(lines)
    
    async def generate_profile_summary(
        self,
        person_name: str,
        messages: list[tuple[datetime, str]]
    ) -> str:
        """Generate a profile summary from a person's messages.
        
        Args:
            person_name: Display name of the person
            messages: List of (timestamp, content) tuples, ordered by timestamp
            
        Returns:
            Generated profile summary text
            
        Raises:
            RateLimitExceeded: If rate limit would be exceeded
            Exception: If AI generation fails
        """
        if not messages:
            return "No messages available to generate a summary."
        
        # Format messages
        formatted_messages = self._format_messages(messages)
        
        # Build prompt
        prompt = self.PROMPT_TEMPLATE.format(
            person_name=person_name,
            messages=formatted_messages
        )
        
        # Estimate tokens (input + estimated output)
        estimated_input_tokens = self._estimate_tokens(prompt)
        estimated_output_tokens = 500  # Rough estimate for 2-3 paragraphs
        estimated_total = estimated_input_tokens + estimated_output_tokens
        
        # Check rate limit
        if not self.rate_limiter.can_use(estimated_total):
            retry_after = self.rate_limiter.time_until_available(estimated_total)
            raise RateLimitExceeded(retry_after)
        
        logger.info(f"Generating profile summary for {person_name} ({len(messages)} messages, ~{estimated_input_tokens} tokens)")
        
        try:
            # Call Gemini API with thinking budget
            response = self.client.models.generate_content(
                model=self.MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=4096,
                    thinking_config=types.ThinkingConfig(
                        thinking_budget=self.THINKING_BUDGET
                    )
                )
            )
            
            # Record actual usage (use estimate if not available)
            actual_tokens = estimated_total
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                actual_tokens = (
                    getattr(response.usage_metadata, 'prompt_token_count', 0) +
                    getattr(response.usage_metadata, 'candidates_token_count', 0)
                )
            
            self.rate_limiter.record_usage(actual_tokens)
            
            # Extract text from response
            if response.text:
                return response.text.strip()
            else:
                logger.warning(f"Empty response from Gemini for {person_name}")
                return "Unable to generate summary at this time."
                
        except Exception as e:
            logger.error(f"Error generating profile summary for {person_name}: {e}")
            raise


# Singleton instance
_ai_service: Optional[AIService] = None


def get_ai_service() -> AIService:
    """Get the AI service singleton.
    
    Must be initialized first by calling init_ai_service().
    """
    global _ai_service
    if _ai_service is None:
        raise RuntimeError("AI service not initialized. Call init_ai_service() first.")
    return _ai_service


def init_ai_service(api_key: str, max_tokens_per_minute: int = 800_000):
    """Initialize the AI service singleton.
    
    Args:
        api_key: Google AI API key
        max_tokens_per_minute: Rate limit (default 800k)
    """
    global _ai_service
    _ai_service = AIService(api_key, max_tokens_per_minute)
    logger.info(f"AI service initialized with {max_tokens_per_minute:,} tokens/min limit")
