"""
SQLAlchemy Models — Source of truth for all persistent data.

Tables:
  - users: User profiles + settings
  - characters: Custom character storage
  - conversations: Chat history per user-character pair
  - memories: Extracted facts (replaces JSON files)
  - affection_states: Relationship progression
"""
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, DateTime,
    ForeignKey, Index, JSON, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True)
    display_name = Column(String(100), default="bạn")
    content_mode = Column(String(20), default="romantic")  # romantic | explicit
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    memories = relationship("Memory", back_populates="user", cascade="all, delete-orphan")
    affection_states = relationship("AffectionRecord", back_populates="user", cascade="all, delete-orphan")


class Conversation(Base):
    """Chat history — one row per message."""
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False)
    character_id = Column(String(64), nullable=False)
    role = Column(String(10), nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    turn_number = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="conversations")

    __table_args__ = (
        Index("ix_conv_user_char", "user_id", "character_id"),
        Index("ix_conv_created", "created_at"),
    )


class Memory(Base):
    """Extracted facts — source of truth (Qdrant is read-cache)."""
    __tablename__ = "memories"

    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False)
    character_id = Column(String(64), nullable=False)
    text = Column(Text, nullable=False)
    type = Column(String(30), default="user_fact")  # user_fact | emotional_state | character_note
    confidence = Column(Float, default=0.8)
    superseded_by = Column(String(36), nullable=True)  # for contradiction resolution
    created_at = Column(DateTime, default=datetime.utcnow)
    last_accessed = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="memories")

    __table_args__ = (
        Index("ix_mem_user_char", "user_id", "character_id"),
        Index("ix_mem_type", "type"),
    )


class SessionSummary(Base):
    """Conversation summaries — compressed context."""
    __tablename__ = "session_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False)
    character_id = Column(String(64), nullable=False)
    summary = Column(Text, nullable=False)
    turn_range = Column(String(20))  # e.g. "1-20"
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_summary_user_char", "user_id", "character_id"),
    )


class AffectionRecord(Base):
    """Relationship state — score + stage + history."""
    __tablename__ = "affection_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False)
    character_id = Column(String(64), nullable=False)
    score = Column(Float, default=0.0)
    stage = Column(String(20), default="stranger")
    total_turns = Column(Integer, default=0)
    history = Column(JSON, default=list)  # list of {delta, reason, turn}
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="affection_states")

    __table_args__ = (
        UniqueConstraint("user_id", "character_id", name="uq_affection_user_char"),
    )


class CustomCharacter(Base):
    """Custom characters created by users."""
    __tablename__ = "custom_characters"

    key = Column(String(64), primary_key=True)
    name = Column(String(100), nullable=False)
    bio = Column(Text)
    system_prompt = Column(Text, nullable=False)
    immersion_prompt = Column(Text)
    immersion_response = Column(Text)
    opening_scene = Column(Text)
    emotional_states = Column(JSON, default=dict)
    content_mode = Column(String(20), default="romantic")
    created_by = Column(String(64))  # user_id
    created_at = Column(DateTime, default=datetime.utcnow)
