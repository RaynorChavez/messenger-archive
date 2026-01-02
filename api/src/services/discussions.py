"""
Discussion Analyzer Service - AI-powered discussion detection using Gemini.

Uses sliding window approach with function calling to classify messages
into thematic discussions.
"""

import json
import logging
import re
import time
from datetime import datetime
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field

from google import genai
from google.genai import types
from sqlalchemy.orm import Session
from sqlalchemy import asc

from ..schemas.discussion import (
    WindowClassificationResponse,
    MessageClassification,
    DiscussionAssignment,
)
from ..db import ImageDescription

logger = logging.getLogger(__name__)


@dataclass
class ActiveDiscussion:
    """Tracks an active discussion during analysis."""
    id: int  # This is now the real DB ID
    title: str
    temp_id: str  # The string ID used by the AI
    message_ids: List[int] = field(default_factory=list)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    ended: bool = False
    # New fields for dormancy and topic tracking
    last_active_window: int = 0  # Track which window last had activity
    dormant: bool = False  # Soft-ended, can be revived
    topic_keywords: List[str] = field(default_factory=list)  # Keywords for topic matching
    recent_participants: List[str] = field(default_factory=list)  # Recent senders


@dataclass
class AnalysisState:
    """State maintained across windows during analysis."""
    active_discussions: Dict[int, ActiveDiscussion] = field(default_factory=dict)
    temp_id_to_db_id: Dict[str, int] = field(default_factory=dict)  # Maps AI temp IDs to DB IDs
    total_tokens_used: int = 0
    windows_processed: int = 0
    current_window: int = 0  # Track current window number


class DiscussionAnalyzer:
    """Analyzes messages to detect thematic discussions using Gemini."""
    
    MODEL = "gemini-3-flash-preview"  # Same model as profile summaries
    WINDOW_SIZE = 300  # Messages per window
    OVERLAP_SIZE = 40  # ~13% overlap
    MAX_MESSAGES_PER_DISCUSSION = 500
    THINKING_BUDGET = 20000
    
    PROMPT_TEMPLATE = '''Analyze these messages from "Manila Dialectics Society" to identify discussion threads.

ACTIVE DISCUSSIONS:
{active_discussions}

MESSAGES TO CLASSIFY:
{messages}

RULES:
- Only assign a message to a discussion if it is ACTUALLY ABOUT that topic - topic relevance is required
- Do NOT assign messages to a discussion just because it is active - check the topic_keywords
- If a message doesn't fit any active discussion, either create a NEW one or leave assignments empty for noise/greetings
- Confidence: LOW (0.3-0.5) for tangentially related, HIGH (0.8-1.0) only for directly on-topic messages
- Use "NEW" as discussion_id to create new discussions (include a descriptive title)
- A discussion can span multiple days - don't end it just because of time gaps
- End a discussion only when the topic has clearly concluded or shifted permanently
- Mark ended discussions in discussions_ended array

OUTPUT STRICT JSON (no markdown, no extra text):
{{"classifications":[{{"message_id":123,"assignments":[{{"discussion_id":1,"title":null,"confidence":0.9}}]}}],"discussions_ended":[],"new_discussions":[{{"temp_id":"NEW_1","title":"Example Title"}}]}}'''

    # Response schema for structured output
    RESPONSE_SCHEMA = {
        "type": "object",
        "properties": {
            "classifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "message_id": {"type": "integer"},
                        "assignments": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "discussion_id": {"type": "string"},
                                    "title": {"type": "string"},
                                    "confidence": {"type": "number"}
                                },
                                "required": ["discussion_id", "confidence"]
                            }
                        }
                    },
                    "required": ["message_id", "assignments"]
                }
            },
            "discussions_ended": {
                "type": "array",
                "items": {"type": "integer"}
            },
            "new_discussions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "temp_id": {"type": "string"},
                        "title": {"type": "string"}
                    },
                    "required": ["temp_id", "title"]
                }
            }
        },
        "required": ["classifications", "discussions_ended", "new_discussions"]
    }

    def __init__(self, api_key: str, db_session: Session, run_id: int, room_id: int):
        """Initialize the analyzer.
        
        Args:
            api_key: Google AI API key
            db_session: SQLAlchemy session for database access
            run_id: The analysis run ID for tracking
            room_id: The room ID to analyze (required, scopes all queries)
        """
        self.client = genai.Client(api_key=api_key)
        self.db = db_session
        self.run_id = run_id
        self.room_id = room_id
        self.state = AnalysisState()
        
        # Define the inspect_discussion tool
        self.inspect_tool = types.FunctionDeclaration(
            name="inspect_discussion",
            description="View all messages in a discussion to understand its context before deciding if a new message belongs to it",
            parameters={
                "type": "object",
                "properties": {
                    "discussion_id": {
                        "type": "integer",
                        "description": "The ID of the discussion to inspect"
                    }
                },
                "required": ["discussion_id"]
            }
        )
        self.tools = [types.Tool(function_declarations=[self.inspect_tool])]
    
    def _format_messages_for_prompt(self, messages: List[Any]) -> str:
        """Format messages as JSON for the prompt, including reply context and image descriptions."""
        from ..db import Message
        
        formatted = []
        for msg in messages:
            # Get content based on message type
            content = self._format_message_content(msg)
            
            # Build message dict
            msg_data = {
                "id": msg.id,
                "timestamp": msg.timestamp.strftime("%Y-%m-%d %H:%M"),
                "sender": msg.sender.display_name if msg.sender else "Unknown",
                "content": content[:500] if content else ""
            }
            
            # Add reply context if this is a reply
            if msg.reply_to_message_id:
                replied_msg = self.db.query(Message).filter(Message.id == msg.reply_to_message_id).first()
                if replied_msg:
                    reply_sender = replied_msg.sender.display_name if replied_msg.sender else "Unknown"
                    reply_content = (replied_msg.content[:100] + "...") if replied_msg.content and len(replied_msg.content) > 100 else (replied_msg.content or "")
                    msg_data["replying_to"] = f'{reply_sender}: "{reply_content}"'
            
            formatted.append(msg_data)
        return json.dumps(formatted, indent=2)
    
    def _format_message_content(self, msg: Any) -> str:
        """Format message content, handling images and other media types."""
        message_type = getattr(msg, 'message_type', 'text') or 'text'
        
        if message_type == 'image':
            # Try to get image description
            if hasattr(msg, 'image_description') and msg.image_description:
                desc = msg.image_description
                content = f"[[Image: {desc.description}]]" if desc.description else "[[Image]]"
                if desc.ocr_text:
                    content += f" [[Text in image: {desc.ocr_text}]]"
                return content
            else:
                # Check DB for description
                img_desc = self.db.query(ImageDescription).filter(
                    ImageDescription.message_id == msg.id
                ).first()
                if img_desc and img_desc.description:
                    content = f"[[Image: {img_desc.description}]]"
                    if img_desc.ocr_text:
                        content += f" [[Text in image: {img_desc.ocr_text}]]"
                    return content
            return "[[Image]]"
        elif message_type == 'video':
            return f"[[Video: {msg.content}]]" if msg.content else "[[Video]]"
        elif message_type == 'audio':
            return f"[[Audio: {msg.content}]]" if msg.content else "[[Audio]]"
        elif message_type == 'file':
            return f"[[File: {msg.content}]]" if msg.content else "[[File]]"
        else:
            return msg.content or ""
    
    def _format_active_discussions(self) -> str:
        """Format active discussions for the prompt, excluding dormant ones."""
        if not self.state.active_discussions:
            return "None yet - this is the first window."
        
        discussions = []
        for disc_id, disc in self.state.active_discussions.items():
            # Skip ended or dormant discussions
            if disc.ended or disc.dormant:
                continue
            
            windows_since_active = self.state.current_window - disc.last_active_window
            discussions.append({
                "id": disc_id,
                "title": disc.title,
                "topic_keywords": disc.topic_keywords[:5] if disc.topic_keywords else [],
                "recent_participants": disc.recent_participants[:3] if disc.recent_participants else [],
                "message_count": len(disc.message_ids),
                "windows_since_active": windows_since_active
            })
        
        if not discussions:
            return "None currently active."
        
        return json.dumps(discussions, indent=2)
    
    def _handle_inspect_discussion(self, discussion_id: int) -> Dict[str, Any]:
        """Handle the inspect_discussion function call."""
        logger.info(f"Inspecting discussion {discussion_id}")
        
        if discussion_id not in self.state.active_discussions:
            return {"error": f"Discussion {discussion_id} not found"}
        
        disc = self.state.active_discussions[discussion_id]
        
        # Fetch the actual messages
        from ..db import Message
        messages = (
            self.db.query(Message)
            .filter(Message.id.in_(disc.message_ids))
            .order_by(asc(Message.timestamp))
            .all()
        )
        
        formatted_messages = []
        for msg in messages:
            # Get content with image descriptions
            content = self._format_message_content(msg)
            
            msg_data = {
                "id": msg.id,
                "sender": msg.sender.display_name if msg.sender else "Unknown",
                "content": content[:300] if content else "",
                "timestamp": msg.timestamp.strftime("%Y-%m-%d %H:%M")
            }
            
            # Add reply context
            if msg.reply_to_message_id:
                replied_msg = self.db.query(Message).filter(Message.id == msg.reply_to_message_id).first()
                if replied_msg:
                    reply_sender = replied_msg.sender.display_name if replied_msg.sender else "Unknown"
                    reply_content = (replied_msg.content[:80] + "...") if replied_msg.content and len(replied_msg.content) > 80 else (replied_msg.content or "")
                    msg_data["replying_to"] = f'{reply_sender}: "{reply_content}"'
            
            formatted_messages.append(msg_data)
        
        return {
            "discussion_id": discussion_id,
            "title": disc.title,
            "message_count": len(disc.message_ids),
            "messages": formatted_messages
        }
    
    def _process_window(self, messages: List[Any]) -> Optional[WindowClassificationResponse]:
        """Process a single window of messages with the AI."""
        
        prompt = self.PROMPT_TEMPLATE.format(
            active_discussions=self._format_active_discussions(),
            messages=self._format_messages_for_prompt(messages)
        )
        
        # Build conversation for potential multi-turn with function calls
        conversation = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
        
        max_turns = 10  # Limit function call turns
        
        for turn in range(max_turns):
            try:
                response = self.client.models.generate_content(
                    model=self.MODEL,
                    contents=conversation,
                    config=types.GenerateContentConfig(
                        tools=self.tools,
                        response_mime_type="application/json",
                        response_schema=self.RESPONSE_SCHEMA,
                        temperature=1.0,
                        max_output_tokens=32768,
                        thinking_config=types.ThinkingConfig(thinking_budget=self.THINKING_BUDGET),
                    )
                )
                
                # Track token usage
                if hasattr(response, 'usage_metadata') and response.usage_metadata:
                    tokens = (
                        getattr(response.usage_metadata, 'prompt_token_count', 0) +
                        getattr(response.usage_metadata, 'candidates_token_count', 0)
                    )
                    self.state.total_tokens_used += tokens
                
                # Check if model wants to call a function
                if response.candidates and response.candidates[0].content.parts:
                    part = response.candidates[0].content.parts[0]
                    
                    if hasattr(part, 'function_call') and part.function_call:
                        func_call = part.function_call
                        logger.info(f"Function call: {func_call.name}({func_call.args})")
                        
                        # Execute the function
                        if func_call.name == "inspect_discussion":
                            result = self._handle_inspect_discussion(func_call.args["discussion_id"])
                        else:
                            result = {"error": f"Unknown function: {func_call.name}"}
                        
                        # Add the function call and response to conversation
                        conversation.append(types.Content(role="model", parts=[part]))
                        conversation.append(types.Content(
                            role="user",
                            parts=[types.Part.from_function_response(
                                name=func_call.name,
                                response=result
                            )]
                        ))
                        continue  # Continue the conversation
                    
                    # We have a text/JSON response
                    if response.text:
                        try:
                            data = json.loads(response.text)
                            return WindowClassificationResponse(**data)
                        except (json.JSONDecodeError, Exception) as e:
                            logger.error(f"Failed to parse response: {e}")
                            logger.error(f"Response text: {response.text[:500]}")
                            return None
                
                break  # No more function calls
                
            except Exception as e:
                logger.error(f"Error processing window: {e}")
                return None
        
        return None
    
    def _generate_topic_keywords(self, title: str, first_message_content: str = "") -> List[str]:
        """Generate topic keywords for a discussion based on title and first message."""
        # Simple keyword extraction from title - no AI call to keep it fast
        # Split title into words, filter out common words
        common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'about', 'from', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'between', 'under', 'over', 'out', 'up', 'down', 'off', 'then', 'than', 'so', 'as', 'if', 'when', 'where', 'why', 'how', 'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those', 'its'}
        
        words = title.lower().replace("'", "").replace('"', '').split()
        keywords = [w.strip('.,!?()[]{}:;') for w in words if w.lower() not in common_words and len(w) > 2]
        
        # Also extract from first message content if available
        if first_message_content:
            content_words = first_message_content.lower().replace("'", "").replace('"', '').split()[:20]
            content_keywords = [w.strip('.,!?()[]{}:;') for w in content_words if w.lower() not in common_words and len(w) > 3]
            keywords.extend(content_keywords[:3])
        
        # Dedupe and limit
        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)
        
        return unique_keywords[:7]
    
    def _create_discussion_in_db(self, temp_id: str, title: str, started_at: Optional[datetime] = None, ended_at: Optional[datetime] = None, first_message_content: str = "", first_sender: str = "") -> int:
        """Create a discussion in the database and return its ID."""
        from ..db import Discussion
        from datetime import timezone
        
        # Use None as default - timestamps will be set from actual message timestamps
        # This ensures ended_at reflects the latest message, not the analysis run time
        # Note: started_at and ended_at are nullable=False in DB, but we'll set them 
        # when the first message is assigned. Use a placeholder for now if not provided.
        now = datetime.now(timezone.utc)
        if started_at is None:
            started_at = now  # Will be corrected when first message is assigned
        if ended_at is None:
            ended_at = datetime.min.replace(tzinfo=timezone.utc)  # Use min date so any message timestamp will be greater
        
        # Generate topic keywords
        topic_keywords = self._generate_topic_keywords(title, first_message_content)
        
        discussion = Discussion(
            room_id=self.room_id,
            analysis_run_id=self.run_id,
            title=title,
            started_at=started_at,
            ended_at=ended_at,
            message_count=0,
            participant_count=0
        )
        self.db.add(discussion)
        self.db.flush()  # Get the ID
        
        db_id = discussion.id
        self.state.temp_id_to_db_id[temp_id] = db_id
        self.state.active_discussions[db_id] = ActiveDiscussion(
            id=db_id,
            title=title,
            temp_id=temp_id,
            message_ids=[],
            started_at=started_at,
            ended_at=ended_at,
            last_active_window=self.state.current_window,
            dormant=False,
            topic_keywords=topic_keywords,
            recent_participants=[first_sender] if first_sender else []
        )
        logger.info(f"Created discussion {db_id}: {title} (keywords: {topic_keywords})")
        return db_id
    
    def _add_message_to_discussion(self, discussion_id: int, message_id: int, confidence: float):
        """Add a message to a discussion in the database."""
        from ..db import DiscussionMessage, Discussion
        
        # Check if already exists
        existing = self.db.query(DiscussionMessage).filter(
            DiscussionMessage.discussion_id == discussion_id,
            DiscussionMessage.message_id == message_id
        ).first()
        
        if existing:
            return
        
        disc_msg = DiscussionMessage(
            discussion_id=discussion_id,
            message_id=message_id,
            confidence=confidence
        )
        self.db.add(disc_msg)
        
        # Update discussion message count
        discussion = self.db.query(Discussion).filter(Discussion.id == discussion_id).first()
        if discussion:
            discussion.message_count = (discussion.message_count or 0) + 1
    
    def _validate_and_log_suspicious(self, classification, assignment, disc, msg) -> None:
        """Log suspicious classifications for review."""
        windows_inactive = self.state.current_window - disc.last_active_window
        
        # Flag: high confidence assignment to discussion inactive for 3+ windows
        if windows_inactive >= 3 and assignment.confidence >= 0.9:
            msg_preview = (msg.content[:50] + "...") if msg.content and len(msg.content) > 50 else (msg.content or "")
            logger.warning(
                f"SUSPICIOUS: msg {classification.message_id} ('{msg_preview}') -> "
                f"discussion '{disc.title}' (inactive {windows_inactive} windows) "
                f"with confidence {assignment.confidence}"
            )
    
    def _update_state_from_response(
        self, 
        response: WindowClassificationResponse,
        messages: List[Any]
    ) -> None:
        """Update analysis state from AI response and write to DB incrementally."""
        from ..db import Discussion, func, Message
        
        message_map = {m.id: m for m in messages}
        
        # Track which discussions received messages in this window
        discussions_active_this_window = set()
        
        # First, create any new discussions declared in new_discussions
        for new_disc in response.new_discussions:
            if new_disc.temp_id not in self.state.temp_id_to_db_id:
                # Try to find first message for this discussion to get content/sender
                first_msg_content = ""
                first_sender = ""
                for cls in response.classifications:
                    for asgn in cls.assignments:
                        if asgn.discussion_id == new_disc.temp_id:
                            msg = message_map.get(cls.message_id)
                            if msg:
                                first_msg_content = msg.content or ""
                                first_sender = msg.sender.display_name if msg.sender else ""
                            break
                    if first_msg_content:
                        break
                
                self._create_discussion_in_db(
                    new_disc.temp_id, 
                    new_disc.title,
                    first_message_content=first_msg_content,
                    first_sender=first_sender
                )
        
        # Process classifications
        for classification in response.classifications:
            msg_id = classification.message_id
            msg = message_map.get(msg_id)
            
            if not msg:
                continue
            
            for assignment in classification.assignments:
                temp_id = assignment.discussion_id
                
                # Resolve temp_id to DB ID
                if isinstance(temp_id, str):
                    if temp_id in self.state.temp_id_to_db_id:
                        db_id = self.state.temp_id_to_db_id[temp_id]
                    elif assignment.title:
                        # Create new discussion for unrecognized temp_id
                        first_msg_content = msg.content or ""
                        first_sender = msg.sender.display_name if msg.sender else ""
                        db_id = self._create_discussion_in_db(
                            temp_id, 
                            assignment.title, 
                            msg.timestamp, 
                            msg.timestamp,
                            first_msg_content,
                            first_sender
                        )
                    else:
                        logger.warning(f"Unknown discussion temp_id {temp_id} with no title, skipping")
                        continue
                elif isinstance(temp_id, int):
                    # Direct DB ID reference (shouldn't happen normally)
                    if temp_id in self.state.active_discussions:
                        db_id = temp_id
                    else:
                        logger.warning(f"Unknown discussion ID {temp_id}, skipping")
                        continue
                else:
                    logger.warning(f"Invalid discussion_id type: {type(temp_id)}, skipping")
                    continue
                
                disc = self.state.active_discussions.get(db_id)
                if not disc:
                    logger.warning(f"Discussion {db_id} not in active state, skipping")
                    continue
                
                # Validation: log suspicious assignments
                self._validate_and_log_suspicious(classification, assignment, disc, msg)
                
                # Check max messages limit
                if len(disc.message_ids) >= self.MAX_MESSAGES_PER_DISCUSSION:
                    logger.warning(f"Discussion {db_id} hit max message limit")
                    continue
                
                # Add message to discussion (both in-memory and DB)
                if msg_id not in disc.message_ids:
                    disc.message_ids.append(msg_id)
                    self._add_message_to_discussion(db_id, msg_id, assignment.confidence)
                
                # Track that this discussion was active
                discussions_active_this_window.add(db_id)
                
                # Update participant list
                sender_name = msg.sender.display_name if msg.sender else "Unknown"
                if sender_name not in disc.recent_participants:
                    disc.recent_participants.append(sender_name)
                    # Keep only most recent 5
                    if len(disc.recent_participants) > 5:
                        disc.recent_participants = disc.recent_participants[-5:]
                
                # Update timestamps
                if disc.started_at is None or msg.timestamp < disc.started_at:
                    disc.started_at = msg.timestamp
                if disc.ended_at is None or msg.timestamp > disc.ended_at:
                    disc.ended_at = msg.timestamp
                
                # Update discussion timestamps in DB
                db_disc = self.db.query(Discussion).filter(Discussion.id == db_id).first()
                if db_disc:
                    if db_disc.started_at is None or msg.timestamp < db_disc.started_at:
                        db_disc.started_at = msg.timestamp
                    if db_disc.ended_at is None or msg.timestamp > db_disc.ended_at:
                        db_disc.ended_at = msg.timestamp
        
        # Update last_active_window for discussions that received messages
        for db_id in discussions_active_this_window:
            if db_id in self.state.active_discussions:
                self.state.active_discussions[db_id].last_active_window = self.state.current_window
                # Revive dormant discussions if they got new messages
                if self.state.active_discussions[db_id].dormant:
                    self.state.active_discussions[db_id].dormant = False
                    logger.info(f"Discussion {db_id} revived from dormancy")
        
        # Check for discussions that should go dormant (5+ windows without activity)
        DORMANCY_THRESHOLD = 5
        for db_id, disc in self.state.active_discussions.items():
            if disc.ended or disc.dormant:
                continue
            windows_inactive = self.state.current_window - disc.last_active_window
            if windows_inactive >= DORMANCY_THRESHOLD:
                disc.dormant = True
                logger.info(f"Discussion {db_id} ('{disc.title}') marked dormant after {windows_inactive} windows of inactivity")
        
        # Mark ended discussions
        for ended_id in response.discussions_ended:
            if ended_id in self.state.active_discussions:
                self.state.active_discussions[ended_id].ended = True
                logger.info(f"Discussion {ended_id} marked as ended")
        
        # Commit all changes for this window
        self.db.commit()
    
    async def analyze_all_messages(
        self,
        update_progress_callback=None
    ) -> Dict[str, Any]:
        """Run full analysis on all messages. Writes to DB incrementally.
        
        Args:
            update_progress_callback: Optional callback(windows_processed, total_windows)
        
        Returns:
            Dict with analysis summary
        """
        from ..db import Message
        
        # Reset state
        self.state = AnalysisState()
        
        # Fetch all messages for this room, ordered by timestamp
        all_messages = (
            self.db.query(Message)
            .filter(Message.room_id == self.room_id)
            .filter(Message.content.isnot(None))
            .filter(Message.content != "")
            .order_by(asc(Message.timestamp))
            .all()
        )
        
        total_messages = len(all_messages)
        logger.info(f"Starting analysis of {total_messages} messages")
        
        if total_messages == 0:
            return {
                "discussions_found": 0,
                "total_tokens": 0,
                "windows_processed": 0
            }
        
        # Calculate windows
        net_per_window = self.WINDOW_SIZE - self.OVERLAP_SIZE
        total_windows = max(1, (total_messages + net_per_window - 1) // net_per_window)
        
        # Process each window
        window_start = 0
        window_number = 0
        while window_start < total_messages:
            window_number += 1
            self.state.current_window = window_number  # Track for dormancy calculations
            
            window_end = min(window_start + self.WINDOW_SIZE, total_messages)
            window_messages = all_messages[window_start:window_end]
            
            logger.info(f"Processing window {window_number}/{total_windows} (messages {window_start}-{window_end})")
            
            # Process window
            response = self._process_window(window_messages)
            
            if response:
                self._update_state_from_response(response, window_messages)
            else:
                logger.warning(f"Failed to process window {self.state.windows_processed + 1}")
            
            self.state.windows_processed += 1
            
            # Update progress
            if update_progress_callback:
                update_progress_callback(self.state.windows_processed, total_windows)
            
            # Move to next window (with overlap)
            window_start += net_per_window
        
        # Return summary (discussions are already in DB)
        return {
            "discussions_found": len(self.state.active_discussions),
            "total_tokens": self.state.total_tokens_used,
            "windows_processed": self.state.windows_processed
        }
    
    # =============================================================================
    # Incremental Analysis
    # =============================================================================
    
    CONTEXT_WINDOWS = 4  # ~120 messages of context for incremental mode
    
    def get_incremental_cutoff(self) -> Optional[int]:
        """Find the message ID to start from for incremental analysis."""
        from ..db import DiscussionAnalysisRun
        from sqlalchemy import desc
        
        # Get last COMPLETED run for this room (not failed or running)
        last_run = self.db.query(DiscussionAnalysisRun).filter(
            DiscussionAnalysisRun.room_id == self.room_id,
            DiscussionAnalysisRun.status == "completed",
            DiscussionAnalysisRun.end_message_id.isnot(None)
        ).order_by(desc(DiscussionAnalysisRun.completed_at)).first()
        
        if not last_run:
            return None  # No valid previous run, must do full
        
        return last_run.end_message_id
    
    def load_incremental_context(self, cutoff_message_id: int) -> tuple:
        """Load context messages and active discussions for incremental run.
        
        Returns:
            (context_messages, active_discussions, context_start_id)
        """
        from ..db import Message, Discussion, DiscussionMessage
        from datetime import timedelta
        
        # Get the cutoff message to find its timestamp
        cutoff_msg = self.db.query(Message).filter(Message.id == cutoff_message_id).first()
        if not cutoff_msg:
            raise ValueError(f"Cutoff message {cutoff_message_id} not found")
        
        context_count = self.CONTEXT_WINDOWS * self.WINDOW_SIZE
        
        # Load context messages for this room (before and including cutoff)
        context_messages = (
            self.db.query(Message)
            .filter(Message.room_id == self.room_id)
            .filter(Message.id <= cutoff_message_id)
            .filter(Message.content.isnot(None))
            .filter(Message.content != "")
            .order_by(Message.id.desc())
            .limit(context_count)
            .all()
        )
        
        # Reverse to chronological order
        context_messages = list(reversed(context_messages))
        context_start_id = context_messages[0].id if context_messages else None
        
        # Load discussions for this room that might still be active
        # Consider discussions that ended within 48h of cutoff as potentially active
        cutoff_time = cutoff_msg.timestamp
        active_discussions = (
            self.db.query(Discussion)
            .filter(Discussion.room_id == self.room_id)
            .filter(Discussion.ended_at >= cutoff_time - timedelta(hours=48))
            .all()
        )
        
        logger.info(f"Loaded {len(context_messages)} context messages, {len(active_discussions)} potentially active discussions")
        
        return context_messages, active_discussions, context_start_id
    
    def rebuild_state_from_db(self, active_discussions: List[Any]) -> None:
        """Rebuild AnalysisState from previous run's discussions."""
        from ..db import Message, DiscussionMessage
        from sqlalchemy import desc
        
        for disc in active_discussions:
            # Get message IDs for this discussion
            msg_links = self.db.query(DiscussionMessage).filter(
                DiscussionMessage.discussion_id == disc.id
            ).all()
            msg_ids = [link.message_id for link in msg_links]
            
            # Generate topic keywords from title
            keywords = self._generate_topic_keywords(disc.title)
            
            # Get recent participants
            if msg_ids:
                recent_msgs = (
                    self.db.query(Message)
                    .filter(Message.id.in_(msg_ids[-20:]))  # Last 20 messages
                    .all()
                )
                participants = list(set(
                    m.sender.display_name for m in recent_msgs 
                    if m.sender and m.sender.display_name
                ))[:5]
            else:
                participants = []
            
            temp_id = f"existing_{disc.id}"
            self.state.active_discussions[disc.id] = ActiveDiscussion(
                id=disc.id,
                title=disc.title,
                temp_id=temp_id,
                message_ids=msg_ids,
                started_at=disc.started_at,
                ended_at=disc.ended_at,
                last_active_window=0,  # Will be updated as we process context
                dormant=False,
                topic_keywords=keywords,
                recent_participants=participants
            )
            self.state.temp_id_to_db_id[temp_id] = disc.id
        
        logger.info(f"Rebuilt state with {len(self.state.active_discussions)} active discussions")
    
    def _process_context_window_readonly(self, messages: List[Any]) -> None:
        """Process a context window to warm up state. Read-only - no DB writes."""
        
        response = self._process_window(messages)
        
        if response:
            # Update in-memory state only - identify which discussions are active
            message_map = {m.id: m for m in messages}
            
            for classification in response.classifications:
                for assignment in classification.assignments:
                    temp_id = assignment.discussion_id
                    
                    # Resolve to DB ID
                    if isinstance(temp_id, str) and temp_id in self.state.temp_id_to_db_id:
                        db_id = self.state.temp_id_to_db_id[temp_id]
                    elif isinstance(temp_id, int) and temp_id in self.state.active_discussions:
                        db_id = temp_id
                    else:
                        continue  # Skip unknown discussions in context
                    
                    disc = self.state.active_discussions.get(db_id)
                    if disc:
                        # Mark as active this window
                        disc.last_active_window = self.state.current_window
                        if disc.dormant:
                            disc.dormant = False
            
            # Check for dormancy
            DORMANCY_THRESHOLD = 5
            for db_id, disc in self.state.active_discussions.items():
                if disc.ended or disc.dormant:
                    continue
                windows_inactive = self.state.current_window - disc.last_active_window
                if windows_inactive >= DORMANCY_THRESHOLD:
                    disc.dormant = True
    
    async def analyze_incremental(
        self,
        update_progress_callback=None
    ) -> Dict[str, Any]:
        """Run incremental analysis on new messages since last completed run.
        
        Args:
            update_progress_callback: Optional callback(windows_processed, total_windows, phase)
        
        Returns:
            Dict with analysis summary
        """
        from ..db import Message
        
        # Find cutoff point
        cutoff_id = self.get_incremental_cutoff()
        
        if cutoff_id is None:
            logger.info("No previous completed run found, falling back to full analysis")
            return await self.analyze_all_messages(update_progress_callback)
        
        # Load context and rebuild state
        context_messages, active_discussions, context_start_id = self.load_incremental_context(cutoff_id)
        
        # Reset state and rebuild from existing discussions
        self.state = AnalysisState()
        self.rebuild_state_from_db(active_discussions)
        
        # Get new messages for this room (after cutoff)
        new_messages = (
            self.db.query(Message)
            .filter(Message.room_id == self.room_id)
            .filter(Message.id > cutoff_id)
            .filter(Message.content.isnot(None))
            .filter(Message.content != "")
            .order_by(asc(Message.timestamp))
            .all()
        )
        
        if not new_messages:
            logger.info("No new messages to analyze")
            return {
                "discussions_found": 0,
                "discussions_extended": 0,
                "new_messages": 0,
                "context_messages": len(context_messages),
                "total_tokens": 0,
                "windows_processed": 0,
                "mode": "incremental"
            }
        
        logger.info(f"Incremental analysis: {len(context_messages)} context, {len(new_messages)} new messages")
        
        # Calculate total windows (context + new)
        net_per_window = self.WINDOW_SIZE - self.OVERLAP_SIZE
        context_windows = max(1, (len(context_messages) + net_per_window - 1) // net_per_window) if context_messages else 0
        new_windows = max(1, (len(new_messages) + net_per_window - 1) // net_per_window)
        total_windows = context_windows + new_windows
        
        # Phase 1: Process context windows (read-only, warms up state)
        logger.info(f"Processing {context_windows} context windows...")
        window_start = 0
        while window_start < len(context_messages):
            self.state.current_window += 1
            window_end = min(window_start + self.WINDOW_SIZE, len(context_messages))
            window_msgs = context_messages[window_start:window_end]
            
            self._process_context_window_readonly(window_msgs)
            self.state.windows_processed += 1
            
            if update_progress_callback:
                update_progress_callback(self.state.windows_processed, total_windows)
            
            window_start += net_per_window
        
        logger.info(f"Context processing complete. Active discussions: {len([d for d in self.state.active_discussions.values() if not d.dormant])}")
        
        # Phase 2: Process new messages (writes to DB)
        discussions_before = set(self.state.active_discussions.keys())
        
        logger.info(f"Processing {new_windows} new message windows...")
        window_start = 0
        while window_start < len(new_messages):
            self.state.current_window += 1
            window_end = min(window_start + self.WINDOW_SIZE, len(new_messages))
            window_msgs = new_messages[window_start:window_end]
            
            logger.info(f"Processing new window {self.state.windows_processed + 1}/{total_windows}")
            
            response = self._process_window(window_msgs)
            
            if response:
                self._update_state_from_response(response, window_msgs)
            else:
                logger.warning(f"Failed to process window {self.state.windows_processed + 1}")
            
            self.state.windows_processed += 1
            
            if update_progress_callback:
                update_progress_callback(self.state.windows_processed, total_windows)
            
            window_start += net_per_window
        
        # Calculate stats
        discussions_after = set(self.state.active_discussions.keys())
        new_discussion_ids = discussions_after - discussions_before
        
        # Get the last message ID for tracking
        end_message_id = new_messages[-1].id if new_messages else cutoff_id
        
        return {
            "discussions_found": len(new_discussion_ids),
            "discussions_extended": len(discussions_before & discussions_after),
            "new_messages": len(new_messages),
            "context_messages": len(context_messages),
            "total_tokens": self.state.total_tokens_used,
            "windows_processed": self.state.windows_processed,
            "mode": "incremental",
            "start_message_id": new_messages[0].id if new_messages else None,
            "end_message_id": end_message_id,
            "context_start_message_id": context_start_id
        }
    
    async def generate_discussion_summary(self, discussion_id: int, title: str, messages: List[Any]) -> str:
        """Generate a summary for a discussion."""
        from ..db import Message
        
        formatted_messages = []
        for msg in messages[:100]:  # Limit for token efficiency
            sender = msg.sender.display_name if msg.sender else 'Unknown'
            content = self._format_message_content(msg)
            
            # Build message line
            line = f"[{msg.timestamp.strftime('%Y-%m-%d %H:%M')}] {sender}"
            
            # Add reply context
            if msg.reply_to_message_id:
                replied_msg = self.db.query(Message).filter(Message.id == msg.reply_to_message_id).first()
                if replied_msg:
                    reply_sender = replied_msg.sender.display_name if replied_msg.sender else "Unknown"
                    reply_content = (replied_msg.content[:50] + "...") if replied_msg.content and len(replied_msg.content) > 50 else (replied_msg.content or "")
                    line += f' (replying to {reply_sender}: "{reply_content}")'
            
            line += f": {content[:300] if content else ''}"
            formatted_messages.append(line)
        
        prompt = f'''Summarize this discussion titled "{title}" from the Manila Dialectics Society philosophy group.

Messages:
{chr(10).join(formatted_messages)}

Write a concise summary (2-3 sentences) capturing the main topics, arguments, and conclusions.'''

        try:
            response = self.client.models.generate_content(
                model=self.MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.5,
                    max_output_tokens=256,
                )
            )
            
            if response.text:
                return response.text.strip()
            
        except Exception as e:
            logger.error(f"Failed to generate summary for discussion {discussion_id}: {e}")
        
        return ""
    
    # =============================================================================
    # Topic Classification
    # =============================================================================
    
    TOPIC_COLORS = [
        '#6366f1',  # Indigo
        '#f43f5e',  # Rose
        '#f59e0b',  # Amber
        '#10b981',  # Emerald
        '#0ea5e9',  # Sky
        '#8b5cf6',  # Violet
        '#14b8a6',  # Teal
        '#f97316',  # Orange
        '#ec4899',  # Pink
        '#06b6d4',  # Cyan
    ]
    
    TOPIC_CLASSIFICATION_SCHEMA = {
        "type": "object",
        "properties": {
            "topics": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"}
                    },
                    "required": ["name", "description"]
                }
            },
            "assignments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "discussion_id": {"type": "integer"},
                        "topic_names": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["discussion_id", "topic_names"]
                }
            }
        },
        "required": ["topics", "assignments"]
    }
    
    TOPIC_CLASSIFICATION_PROMPT = '''You are classifying discussions from "Manila Dialectics Society", a Filipino philosophy discussion group. They discuss philosophy, politics, culture, history, and intellectual discourse.

EXISTING TOPICS (reuse if appropriate, modify descriptions, or create new ones):
{existing_topics}

DISCUSSIONS TO CLASSIFY:
{discussions}

Create 5-10 topic categories that best organize this content. Each discussion should belong to 1-3 topics.

Guidelines:
- Reuse existing topic names when they fit
- Create new topics for themes not covered
- Topics should be broad enough to group multiple discussions
- Each topic needs a concise description (1 sentence)

Output JSON with topics and assignments.'''

    async def classify_topics(
        self,
        update_progress_callback=None
    ) -> Dict[str, Any]:
        """Classify all discussions for this room into topics using AI."""
        from ..db import Discussion, Topic, DiscussionTopic
        from ..schemas.discussion import TopicClassificationAIResponse
        
        # Fetch all discussions for this room
        discussions = self.db.query(Discussion).filter(Discussion.room_id == self.room_id).all()
        
        if not discussions:
            return {
                "topics_created": 0,
                "discussions_classified": 0
            }
        
        # Format discussions for prompt
        discussions_data = []
        for d in discussions:
            discussions_data.append({
                "id": d.id,
                "title": d.title,
                "summary": d.summary or ""
            })
        
        # Fetch existing topics for this room
        existing_topics = self.db.query(Topic).filter(Topic.room_id == self.room_id).all()
        existing_topics_data = [{"name": t.name, "description": t.description or ""} for t in existing_topics]
        
        # Build prompt
        prompt = self.TOPIC_CLASSIFICATION_PROMPT.format(
            existing_topics=json.dumps(existing_topics_data, indent=2) if existing_topics_data else "None yet.",
            discussions=json.dumps(discussions_data, indent=2)
        )
        
        try:
            response = self.client.models.generate_content(
                model=self.MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=self.TOPIC_CLASSIFICATION_SCHEMA,
                    temperature=1.0,
                    max_output_tokens=16384,  # Increased for large discussion lists
                    thinking_config=types.ThinkingConfig(thinking_budget=self.THINKING_BUDGET),
                )
            )
            
            if not response.text:
                raise ValueError("Empty response from AI")
            
            # Try to parse JSON, with repair attempts if it fails
            response_text = response.text
            try:
                data = json.loads(response_text)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse failed, attempting repair: {e}")
                # Try to repair common issues
                # 1. Remove trailing commas before } or ]
                repaired = re.sub(r',(\s*[}\]])', r'\1', response_text)
                # 2. Try to truncate at last complete object if response was cut off
                if '"assignments"' in repaired:
                    # Find the last complete assignment object
                    last_good = repaired.rfind('}]')
                    if last_good > 0:
                        repaired = repaired[:last_good + 2] + '}'
                try:
                    data = json.loads(repaired)
                    logger.info("JSON repair successful")
                except json.JSONDecodeError:
                    # If still failing, re-raise original error
                    raise e
            
            ai_response = TopicClassificationAIResponse(**data)
            
            # Clear existing discussion-topic links
            self.db.query(DiscussionTopic).delete()
            self.db.commit()
            
            # Create/update topics
            topic_name_to_id = {}
            existing_topic_names = {t.name.lower(): t for t in existing_topics}
            color_index = len(existing_topics) % len(self.TOPIC_COLORS)
            
            for topic_def in ai_response.topics:
                existing = existing_topic_names.get(topic_def.name.lower())
                if existing:
                    # Update description if changed
                    existing.description = topic_def.description
                    topic_name_to_id[topic_def.name] = existing.id
                else:
                    # Create new topic for this room
                    new_topic = Topic(
                        room_id=self.room_id,
                        name=topic_def.name,
                        description=topic_def.description,
                        color=self.TOPIC_COLORS[color_index % len(self.TOPIC_COLORS)]
                    )
                    self.db.add(new_topic)
                    self.db.flush()
                    topic_name_to_id[topic_def.name] = new_topic.id
                    color_index += 1
            
            self.db.commit()
            
            # Create assignments
            discussions_classified = 0
            for assignment in ai_response.assignments:
                for topic_name in assignment.topic_names:
                    topic_id = topic_name_to_id.get(topic_name)
                    if topic_id:
                        link = DiscussionTopic(
                            discussion_id=assignment.discussion_id,
                            topic_id=topic_id
                        )
                        self.db.add(link)
                discussions_classified += 1
            
            self.db.commit()
            
            # Delete orphaned topics (topics with no discussions)
            orphaned = self.db.query(Topic).filter(
                ~Topic.id.in_(
                    self.db.query(DiscussionTopic.topic_id).distinct()
                )
            ).all()
            for topic in orphaned:
                self.db.delete(topic)
            self.db.commit()
            
            # Get all topic IDs that were created/updated
            all_topic_ids = list(topic_name_to_id.values())
            
            return {
                "topics_created": len(ai_response.topics),
                "discussions_classified": discussions_classified,
                "topic_ids": all_topic_ids
            }
            
        except Exception as e:
            logger.error(f"Topic classification failed: {e}")
            raise
