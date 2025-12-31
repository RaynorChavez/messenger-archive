"""
Virtual Chat Service - AI-powered group chat with persona agents.

Uses Gemini to roleplay as archived people based on their message history
and communication style.
"""

import json
import asyncio
import logging
import queue
import threading
from datetime import datetime
from typing import Optional, List, Dict, Set, AsyncGenerator, Any
from dataclasses import dataclass, field

from google import genai
from google.genai import types
from sqlalchemy.orm import Session
from sqlalchemy import and_

from ..db import Person, Message, VirtualConversation, VirtualParticipant, VirtualMessage
from ..config import get_settings

logger = logging.getLogger(__name__)


# =============================================================================
# Persona Prompt Template
# =============================================================================

SYSTEM_INSTRUCTION = """You roleplay as a specific person in casual chat. Mimic EXACTLY how they write.

The example messages show:
- [PersonName]: = messages FROM the person you're roleplaying. COPY THIS STYLE.
- [someone]: = messages from other people. IGNORE their style, only use for context.

COPY THE PERSON'S STYLE:
- Their spelling, punctuation, lowercase/uppercase, emoji habits
- Their language mixing (English/Tagalog/etc) 
- Their message length patterns - short for casual, long only when THEY go deep
- Their slang, "lol", "haha", fragments - whatever THEY use

DO NOT:
- Sound like an AI or formal assistant
- Add "(edited)" or timestamps
- Include "[Name]:" prefix in your response - that's just labeling in examples
- Greet/welcome people robotically
- Copy how [someone] messages are written - those are OTHER people

If nothing natural to say: [NO RESPONSE]

OUTPUT: Just the message text, nothing else."""

PERSONA_TEMPLATE = """You ARE {name} in a group chat.

{summary}
{notes_section}
## {name}'s ACTUAL messages (copy this style):

{messages_with_context}

---
Respond to the chat below AS {name}. Match their vibe exactly - casual or intellectual depending on topic."""


# =============================================================================
# Persona Cache
# =============================================================================

@dataclass
class CachedPersona:
    """Cached persona context for a person."""
    person_id: int
    display_name: str
    context: str  # Full persona context (system prompt + messages)
    created_at: datetime = field(default_factory=datetime.now)


class PersonaCache:
    """In-memory cache for built persona contexts."""
    
    def __init__(self):
        self._cache: Dict[int, CachedPersona] = {}
    
    def get(self, person_id: int) -> Optional[CachedPersona]:
        """Get cached persona context."""
        return self._cache.get(person_id)
    
    def set(self, person_id: int, display_name: str, context: str):
        """Cache a persona context."""
        self._cache[person_id] = CachedPersona(
            person_id=person_id,
            display_name=display_name,
            context=context
        )
    
    def invalidate(self, person_id: int):
        """Invalidate a persona's cache (e.g., when profile summary regenerated)."""
        self._cache.pop(person_id, None)
        logger.info(f"Invalidated persona cache for person {person_id}")
    
    def clear(self):
        """Clear all cached personas."""
        self._cache.clear()


# Global persona cache instance
_persona_cache = PersonaCache()


def get_persona_cache() -> PersonaCache:
    """Get the global persona cache instance."""
    return _persona_cache


# =============================================================================
# Persona Builder
# =============================================================================

class PersonaBuilder:
    """Builds persona prompts from archived messages."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def build_persona_context(self, person_id: int) -> tuple[str, str]:
        """Build complete persona context for a person.
        
        Returns:
            (display_name, full_context)
        """
        # Check cache first
        cache = get_persona_cache()
        cached = cache.get(person_id)
        if cached:
            logger.debug(f"Using cached persona for {cached.display_name}")
            return cached.display_name, cached.context
        
        # Get person
        person = self.db.query(Person).filter(Person.id == person_id).first()
        if not person:
            raise ValueError(f"Person {person_id} not found")
        
        display_name = person.display_name or f"Person {person_id}"
        summary = person.ai_summary or "No profile summary available."
        
        # Build notes section if available
        notes_section = ""
        if person.notes and person.notes.strip():
            notes_section = f"\n## Additional notes about {display_name}:\n{person.notes.strip()}\n"
        
        # Build messages with context
        messages_with_context = self._build_messages_with_context(person_id, display_name)
        
        # Build full context
        context = PERSONA_TEMPLATE.format(
            name=display_name,
            summary=summary,
            notes_section=notes_section,
            messages_with_context=messages_with_context
        )
        
        # Cache it
        cache.set(person_id, display_name, context)
        logger.info(f"Built and cached persona for {display_name} ({len(context)} chars)")
        
        return display_name, context
    
    def _build_messages_with_context(self, person_id: int, person_name: str) -> str:
        """Build all messages with 3 before/after context, deduplicated."""
        
        # Get all messages by this person, ordered by timestamp
        person_messages = self.db.query(Message).filter(
            Message.sender_id == person_id,
            Message.content.isnot(None),
            Message.content != ""
        ).order_by(Message.timestamp).all()
        
        if not person_messages:
            return "(No messages found)"
        
        seen_context_ids: Set[int] = set()
        formatted_sections = []
        
        for i, msg in enumerate(person_messages):
            # Get 3 messages before (excluding already-seen and self)
            before = self.db.query(Message).filter(
                Message.timestamp < msg.timestamp,
                Message.id != msg.id,
                Message.content.isnot(None),
                Message.content != ""
            ).order_by(Message.timestamp.desc()).limit(3).all()
            before.reverse()  # Chronological order
            
            # Filter out already-seen
            before = [m for m in before if m.id not in seen_context_ids]
            
            # Get 3 messages after
            after = self.db.query(Message).filter(
                Message.timestamp > msg.timestamp,
                Message.id != msg.id,
                Message.content.isnot(None),
                Message.content != ""
            ).order_by(Message.timestamp.asc()).limit(3).all()
            
            # Filter out already-seen
            after = [m for m in after if m.id not in seen_context_ids]
            
            # Mark all as seen (including the person's message)
            seen_context_ids.update(m.id for m in before)
            seen_context_ids.update(m.id for m in after)
            seen_context_ids.add(msg.id)
            
            # Format this section
            section = self._format_message_section(msg, before, after, person_name)
            formatted_sections.append(section)
        
        return "\n\n---\n\n".join(formatted_sections)
    
    def _format_message_section(
        self, 
        msg: Message, 
        before: List[Message], 
        after: List[Message],
        person_name: str
    ) -> str:
        """Format a single message with its context.
        
        Only show the person's message prominently. Context from others
        is shown generically to avoid style contamination.
        """
        lines = []
        
        # Context before (generic, don't copy their style)
        if before:
            for m in before:
                content = self._truncate(m.content, 200)
                lines.append(f"[someone]: {content}")
        
        # The person's message - THIS IS WHAT TO COPY
        content = self._truncate(msg.content, 500)
        lines.append(f"[{person_name}]: {content}")
        
        # Context after (generic)
        if after:
            for m in after:
                content = self._truncate(m.content, 200)
                lines.append(f"[someone]: {content}")
        
        return "\n".join(lines)
    
    def _clean_content(self, text: str) -> str:
        """Clean message content for persona context."""
        if not text:
            return ""
        # Strip (edited) markers
        text = text.replace(" (edited)", "").replace("(edited)", "")
        return text.strip()
    
    def _truncate(self, text: str, max_len: int) -> str:
        """Truncate text to max length."""
        text = self._clean_content(text)
        if not text:
            return ""
        if len(text) <= max_len:
            return text
        return text[:max_len] + "..."


# =============================================================================
# Virtual Chat Service
# =============================================================================

class VirtualChatService:
    """Manages virtual chat conversations and agent responses."""
    
    MODEL = "gemini-3-flash-preview"
    
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
    
    def create_conversation(self, db: Session, participant_ids: List[int]) -> VirtualConversation:
        """Create a new virtual conversation."""
        # Validate participants exist
        people = db.query(Person).filter(Person.id.in_(participant_ids)).all()
        if len(people) != len(participant_ids):
            found_ids = {p.id for p in people}
            missing = set(participant_ids) - found_ids
            raise ValueError(f"People not found: {missing}")
        
        # Create conversation
        conversation = VirtualConversation()
        db.add(conversation)
        db.flush()  # Get the ID
        
        # Add participants
        for person_id in participant_ids:
            participant = VirtualParticipant(
                conversation_id=conversation.id,
                person_id=person_id
            )
            db.add(participant)
        
        db.commit()
        db.refresh(conversation)
        
        logger.info(f"Created virtual conversation {conversation.id} with {len(participant_ids)} participants")
        return conversation
    
    def get_conversation(self, db: Session, conversation_id: int) -> Optional[VirtualConversation]:
        """Get a conversation by ID."""
        return db.query(VirtualConversation).filter(
            VirtualConversation.id == conversation_id
        ).first()
    
    def add_participant(self, db: Session, conversation_id: int, person_id: int) -> VirtualParticipant:
        """Add a participant to an existing conversation."""
        # Check if already a participant
        existing = db.query(VirtualParticipant).filter(
            VirtualParticipant.conversation_id == conversation_id,
            VirtualParticipant.person_id == person_id
        ).first()
        
        if existing:
            return existing
        
        participant = VirtualParticipant(
            conversation_id=conversation_id,
            person_id=person_id
        )
        db.add(participant)
        db.commit()
        db.refresh(participant)
        
        return participant
    
    async def process_message(
        self,
        db: Session,
        conversation_id: int,
        content: str
    ) -> AsyncGenerator[str, None]:
        """Process a user message and stream agent responses.
        
        Yields SSE-formatted events.
        """
        # Get conversation
        conversation = self.get_conversation(db, conversation_id)
        if not conversation:
            yield self._sse_event("error", {"message": "Conversation not found"})
            return
        
        # Save user message
        user_msg = VirtualMessage(
            conversation_id=conversation_id,
            sender_type="user",
            person_id=None,
            content=content
        )
        db.add(user_msg)
        db.commit()
        db.refresh(user_msg)
        
        yield self._sse_event("user_message", {"id": user_msg.id, "content": content})
        
        # Get participants
        participants = db.query(VirtualParticipant).filter(
            VirtualParticipant.conversation_id == conversation_id
        ).all()
        
        if not participants:
            yield self._sse_event("complete", {})
            return
        
        # Get conversation history
        history = db.query(VirtualMessage).filter(
            VirtualMessage.conversation_id == conversation_id
        ).order_by(VirtualMessage.created_at).all()
        
        # Build persona contexts (this will use cache)
        persona_builder = PersonaBuilder(db)
        
        # Create async tasks for each agent
        async def stream_agent(participant: VirtualParticipant):
            """Stream responses from a single agent."""
            try:
                person = participant.person
                display_name = person.display_name or f"Person {person.id}"
                
                # Emit thinking event
                yield self._sse_event("thinking", {
                    "person_id": person.id,
                    "display_name": display_name
                })
                
                # Build persona context
                _, persona_context = persona_builder.build_persona_context(person.id)
                
                # Build conversation history text
                history_text = self._format_conversation_history(history[:-1])  # Exclude the just-added message
                
                # Build the user prompt (conversation context)
                user_prompt = f"## Current Conversation\n{history_text}\n\nUser: {content}\n\nRespond as {display_name}:"
                
                # Stream response from Gemini with system instruction
                # Run in thread to avoid blocking the event loop
                response_text = ""
                chunk_queue: queue.Queue = queue.Queue()
                
                def run_generation():
                    """Run the blocking Gemini call in a thread."""
                    try:
                        response = self.client.models.generate_content_stream(
                            model=self.MODEL,
                            contents=user_prompt,
                            config=types.GenerateContentConfig(
                                system_instruction=f"{SYSTEM_INSTRUCTION}\n\n{persona_context}",
                                temperature=1.0,
                                max_output_tokens=4096,
                                thinking_config=types.ThinkingConfig(
                                    thinking_budget=128
                                ),
                            )
                        )
                        for chunk in response:
                            if chunk.text:
                                chunk_queue.put(("chunk", chunk.text))
                        chunk_queue.put(("done", None))
                    except Exception as e:
                        chunk_queue.put(("error", str(e)))
                
                # Start generation in background thread
                thread = threading.Thread(target=run_generation, daemon=True)
                thread.start()
                
                # Yield chunks as they arrive (non-blocking)
                try:
                    while True:
                        # Use asyncio-friendly polling
                        while chunk_queue.empty():
                            await asyncio.sleep(0.01)  # Yield to event loop
                        
                        msg_type, data = chunk_queue.get_nowait()
                        
                        if msg_type == "done":
                            break
                        elif msg_type == "error":
                            logger.error(f"Error generating response for {display_name}: {data}")
                            yield self._sse_event("error", {"message": f"Error from {display_name}: {data}"})
                            return
                        elif msg_type == "chunk":
                            response_text += data
                            yield self._sse_event("chunk", {
                                "person_id": person.id,
                                "text": data
                            })
                except Exception as e:
                    logger.error(f"Error generating response for {display_name}: {e}")
                    yield self._sse_event("error", {"message": f"Error from {display_name}: {str(e)}"})
                    return
                
                # Check if agent chose not to respond
                response_text = response_text.strip()
                message_id = None
                
                if response_text and response_text != "[NO RESPONSE]":
                    # Save agent message
                    agent_msg = VirtualMessage(
                        conversation_id=conversation_id,
                        sender_type="agent",
                        person_id=person.id,
                        content=response_text
                    )
                    db.add(agent_msg)
                    db.commit()
                    db.refresh(agent_msg)
                    message_id = agent_msg.id
                
                yield self._sse_event("agent_done", {
                    "person_id": person.id,
                    "message_id": message_id
                })
                
            except Exception as e:
                logger.error(f"Error in agent stream: {e}")
                yield self._sse_event("error", {"message": str(e)})
        
        # Interleave all agent streams
        async for event in self._interleave_agent_streams(
            [stream_agent(p) for p in participants]
        ):
            yield event
        
        yield self._sse_event("complete", {})
    
    async def _interleave_agent_streams(
        self, 
        streams: List[AsyncGenerator[str, None]]
    ) -> AsyncGenerator[str, None]:
        """Interleave multiple async generators, yielding events as they arrive."""
        
        # Convert generators to async iterators and create initial tasks
        iterators = [s.__aiter__() for s in streams]
        pending: Dict[asyncio.Task, int] = {}  # task -> iterator index
        
        # Create initial tasks for each iterator
        for i, it in enumerate(iterators):
            task = asyncio.create_task(it.__anext__())
            pending[task] = i
        
        while pending:
            # Wait for any task to complete
            done, _ = await asyncio.wait(
                pending.keys(),
                return_when=asyncio.FIRST_COMPLETED
            )
            
            for task in done:
                idx = pending.pop(task)
                try:
                    event = task.result()
                    yield event
                    # Schedule next item from this iterator
                    new_task = asyncio.create_task(iterators[idx].__anext__())
                    pending[new_task] = idx
                except StopAsyncIteration:
                    # This iterator is exhausted
                    pass
                except Exception as e:
                    logger.error(f"Error in stream {idx}: {e}")
    
    def _format_conversation_history(self, messages: List[VirtualMessage]) -> str:
        """Format conversation history for the prompt."""
        if not messages:
            return "(No previous messages)"
        
        lines = []
        for msg in messages:
            if msg.sender_type == "user":
                lines.append(f"User: {msg.content}")
            else:
                sender_name = msg.person.display_name if msg.person else "Agent"
                lines.append(f"{sender_name}: {msg.content}")
        
        return "\n".join(lines)
    
    def _sse_event(self, event_type: str, data: dict) -> str:
        """Format an SSE event."""
        data["type"] = event_type
        return f"data: {json.dumps(data)}\n\n"


# =============================================================================
# Service Singleton
# =============================================================================

_virtual_chat_service: Optional[VirtualChatService] = None


def get_virtual_chat_service() -> VirtualChatService:
    """Get the virtual chat service singleton."""
    global _virtual_chat_service
    if _virtual_chat_service is None:
        settings = get_settings()
        _virtual_chat_service = VirtualChatService(api_key=settings.gemini_api_key)
    return _virtual_chat_service


def init_virtual_chat_service(api_key: str):
    """Initialize the virtual chat service singleton."""
    global _virtual_chat_service
    _virtual_chat_service = VirtualChatService(api_key=api_key)
