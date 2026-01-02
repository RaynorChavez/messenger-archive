from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Float, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from sqlalchemy.sql import func
from typing import Generator
from pgvector.sqlalchemy import Vector

from .config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# =============================================================================
# Models
# =============================================================================

class Person(Base):
    __tablename__ = "people"
    
    id = Column(Integer, primary_key=True, index=True)
    matrix_user_id = Column(String, unique=True, nullable=False, index=True)
    display_name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    fb_profile_url = Column(String, nullable=True)
    fb_name = Column(String, nullable=True)  # Original FB name from export (for matching)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # AI Summary fields
    ai_summary = Column(Text, nullable=True)
    ai_summary_generated_at = Column(DateTime(timezone=True), nullable=True)
    ai_summary_message_count = Column(Integer, default=0)
    
    messages = relationship("Message", back_populates="sender")


class Room(Base):
    __tablename__ = "rooms"
    
    id = Column(Integer, primary_key=True, index=True)
    matrix_room_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=True)
    is_group = Column(Boolean, default=True)
    avatar_url = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    display_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    messages = relationship("Message", back_populates="room")
    members = relationship("RoomMember", back_populates="room")


class RoomMember(Base):
    """Tracks which people are members of which rooms with per-room stats."""
    __tablename__ = "room_members"
    
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    person_id = Column(Integer, ForeignKey("people.id", ondelete="CASCADE"), nullable=False)
    first_seen_at = Column(DateTime(timezone=True), nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    message_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    room = relationship("Room", back_populates="members")
    person = relationship("Person")
    
    __table_args__ = (
        UniqueConstraint('room_id', 'person_id', name='uq_room_member'),
    )


class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    matrix_event_id = Column(String, unique=True, nullable=False, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=True)
    sender_id = Column(Integer, ForeignKey("people.id", ondelete="SET NULL"), nullable=True)
    content = Column(Text, nullable=True)
    reply_to_message_id = Column(Integer, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    room = relationship("Room", back_populates="messages")
    sender = relationship("Person", back_populates="messages")
    reply_to = relationship("Message", remote_side=[id], foreign_keys=[reply_to_message_id])
    discussion_links = relationship("DiscussionMessage", back_populates="message")


class DiscussionAnalysisRun(Base):
    __tablename__ = "discussion_analysis_runs"
    
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, default="running")  # running, completed, failed
    windows_processed = Column(Integer, default=0)
    total_windows = Column(Integer, nullable=True)
    discussions_found = Column(Integer, default=0)
    tokens_used = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    # Incremental analysis fields
    mode = Column(String(20), default="full")  # 'full' or 'incremental'
    start_message_id = Column(Integer, nullable=True)  # First new message analyzed (NULL for full)
    end_message_id = Column(Integer, nullable=True)  # Last message analyzed
    context_start_message_id = Column(Integer, nullable=True)  # Start of context window (for incremental)
    new_messages_count = Column(Integer, default=0)  # Count of new messages processed
    context_messages_count = Column(Integer, default=0)  # Count of context messages loaded
    
    room = relationship("Room")
    discussions = relationship("Discussion", back_populates="analysis_run", cascade="all, delete-orphan")


class Discussion(Base):
    __tablename__ = "discussions"
    
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    analysis_run_id = Column(Integer, ForeignKey("discussion_analysis_runs.id", ondelete="CASCADE"), nullable=True)
    title = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=False)
    message_count = Column(Integer, default=0)
    participant_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    room = relationship("Room")
    analysis_run = relationship("DiscussionAnalysisRun", back_populates="discussions")
    message_links = relationship("DiscussionMessage", back_populates="discussion", cascade="all, delete-orphan")
    topics = relationship("Topic", secondary="discussion_topics", back_populates="discussions")


class DiscussionMessage(Base):
    __tablename__ = "discussion_messages"
    
    discussion_id = Column(Integer, ForeignKey("discussions.id", ondelete="CASCADE"), primary_key=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True)
    confidence = Column(Float, default=1.0)
    
    discussion = relationship("Discussion", back_populates="message_links")
    message = relationship("Message", back_populates="discussion_links")


class Topic(Base):
    __tablename__ = "topics"
    
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    color = Column(String(7), nullable=False)  # Hex color e.g. #6366f1
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    room = relationship("Room")
    discussions = relationship("Discussion", secondary="discussion_topics", back_populates="topics")
    
    __table_args__ = (
        UniqueConstraint('name', 'room_id', name='topics_name_room_unique'),
    )


class DiscussionTopic(Base):
    __tablename__ = "discussion_topics"
    
    discussion_id = Column(Integer, ForeignKey("discussions.id", ondelete="CASCADE"), primary_key=True)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True)


class TopicClassificationRun(Base):
    __tablename__ = "topic_classification_runs"
    
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), default="running")  # running, completed, failed
    topics_created = Column(Integer, default=0)
    discussions_classified = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    
    room = relationship("Room")


class Embedding(Base):
    """Vector embeddings for semantic search."""
    __tablename__ = "embeddings"
    
    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String(50), nullable=False)  # 'message', 'discussion', 'person', 'topic'
    entity_id = Column(Integer, nullable=False)
    content_hash = Column(String(64), nullable=True)  # SHA256 hash for change detection
    embedding = Column(Vector(768), nullable=True)  # Gemini text-embedding-004 = 768 dimensions
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        UniqueConstraint('entity_type', 'entity_id', name='uq_embedding_entity'),
    )


# =============================================================================
# Virtual Chat Models
# =============================================================================

class VirtualConversation(Base):
    """A virtual chat conversation with AI personas."""
    __tablename__ = "virtual_conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    participants = relationship("VirtualParticipant", back_populates="conversation", cascade="all, delete-orphan")
    messages = relationship("VirtualMessage", back_populates="conversation", cascade="all, delete-orphan")


class VirtualParticipant(Base):
    """A person participating in a virtual conversation as an AI agent."""
    __tablename__ = "virtual_participants"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("virtual_conversations.id", ondelete="CASCADE"), nullable=False)
    person_id = Column(Integer, ForeignKey("people.id", ondelete="CASCADE"), nullable=False)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    
    conversation = relationship("VirtualConversation", back_populates="participants")
    person = relationship("Person")
    
    __table_args__ = (
        UniqueConstraint('conversation_id', 'person_id', name='uq_virtual_participant'),
    )


class VirtualMessage(Base):
    """A message in a virtual conversation (from user or AI agent)."""
    __tablename__ = "virtual_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("virtual_conversations.id", ondelete="CASCADE"), nullable=False)
    sender_type = Column(String(20), nullable=False)  # 'user' or 'agent'
    person_id = Column(Integer, ForeignKey("people.id", ondelete="SET NULL"), nullable=True)  # NULL for user
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    conversation = relationship("VirtualConversation", back_populates="messages")
    person = relationship("Person")


# =============================================================================
# Database Dependency
# =============================================================================

def get_db() -> Generator[Session, None, None]:
    """Dependency that provides a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
