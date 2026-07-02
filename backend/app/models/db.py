"""SQLAlchemy ORM models for TutorLoop-AI."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

VECTOR_DIM = 384


def _vector_column():
    try:
        from pgvector.sqlalchemy import Vector

        return mapped_column(Vector(VECTOR_DIM), nullable=True)
    except Exception:  # pragma: no cover - pgvector may not be installed
        return mapped_column(JSONB, nullable=True)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="student")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=now_utc)


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    video_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    config_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=now_utc)

    videos: Mapped[list["Video"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    knowledge_nodes: Mapped[list["KnowledgeNode"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    rooms: Mapped[list["Room"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    materials: Mapped[list["CourseMaterial"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    transcript_json: Mapped[Optional[list[dict]]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="processing")
    created_at: Mapped[datetime] = mapped_column(default=now_utc)

    course: Mapped["Course"] = relationship(back_populates="videos")
    frames: Mapped[list["VideoFrame"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )


class VideoFrame(Base):
    __tablename__ = "video_frames"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    video_id: Mapped[str] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    timestamp_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding = _vector_column()

    video: Mapped["Video"] = relationship(back_populates="frames")


class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"

    __table_args__ = (
        # Prevent duplicate nodes when build-graph is re-run: the same
        # (course, name) pair must resolve to a single node.
        UniqueConstraint("course_id", "name", name="uq_knowledge_node_course_name"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    threshold: Mapped[float] = mapped_column(Float, default=0.8)
    neo4j_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    position_x: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    position_y: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    embedding = _vector_column()
    created_at: Mapped[datetime] = mapped_column(default=now_utc)

    course: Mapped["Course"] = relationship(back_populates="knowledge_nodes")
    mastery_records: Mapped[list["Mastery"]] = relationship(
        back_populates="node", cascade="all, delete-orphan"
    )


class KnowledgeEdge(Base):
    __tablename__ = "knowledge_edges"

    __table_args__ = (
        UniqueConstraint(
            "course_id", "source_id", "target_id", "relation",
            name="uq_knowledge_edge"
        ),
        Index("ix_knowledge_edges_course_id", "course_id"),
        Index("ix_knowledge_edges_source_id", "source_id"),
        Index("ix_knowledge_edges_target_id", "target_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False
    )
    target_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False
    )
    relation: Mapped[str] = mapped_column(String(64), default="prerequisite")
    created_at: Mapped[datetime] = mapped_column(default=now_utc)


class Mastery(Base):
    __tablename__ = "mastery"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    node_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), primary_key=True
    )
    p_known: Mapped[float] = mapped_column(Float, default=0.3)
    p_t: Mapped[float] = mapped_column(Float, default=0.3)
    p_g: Mapped[float] = mapped_column(Float, default=0.2)
    p_s: Mapped[float] = mapped_column(Float, default=0.1)
    p_l0: Mapped[float] = mapped_column(Float, default=0.1)
    interactions_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(default=now_utc)

    node: Mapped["KnowledgeNode"] = relationship(back_populates="mastery_records")


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    slug: Mapped[str] = mapped_column(
        String(16), unique=True, nullable=False, index=True
    )
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    allow_anonymous: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    entry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    welcome_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    max_participants: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    config_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(default=now_utc, onupdate=now_utc)

    course: Mapped["Course"] = relationship(back_populates="rooms")


class Interaction(Base):
    __tablename__ = "interactions"

    __table_args__ = (
        Index("ix_interactions_course_id", "course_id"),
        Index("ix_interactions_user_id", "user_id"),
        Index("ix_interactions_created_at", "created_at"),
        Index("ix_interactions_course_created", "course_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # Foreign keys with SET NULL so deleting a user/course/video/node does not
    # leave dangling interaction rows that silently skew class reports.
    # user_id stays nullable (anonymous interactions) and is SET NULL on user
    # deletion rather than CASCADE, preserving historical anonymous-ish data.
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    room_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True
    )
    course_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), nullable=True
    )
    video_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("videos.id", ondelete="SET NULL"), nullable=True
    )
    node_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("knowledge_nodes.id", ondelete="SET NULL"), nullable=True
    )
    video_timestamp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    screenshot_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    question_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    answer_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_correct: Mapped[Optional[bool]] = mapped_column(nullable=True)
    help_count: Mapped[int] = mapped_column(Integer, default=0)
    watch_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=now_utc)


class RoomEntrySession(Base):
    __tablename__ = "room_entry_sessions"

    __table_args__ = (
        UniqueConstraint("room_id", "session_id", name="uq_room_entry_session"),
        Index("ix_room_entry_sessions_room_id", "room_id"),
        Index("ix_room_entry_sessions_session_id", "session_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    room_id: Mapped[str] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=now_utc)


class CourseMaterial(Base):
    __tablename__ = "course_materials"

    __table_args__ = (
        Index("ix_course_materials_course_id", "course_id"),
        Index("ix_course_materials_file_type", "file_type"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(16), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="processing")
    created_at: Mapped[datetime] = mapped_column(default=now_utc)

    course: Mapped["Course"] = relationship(back_populates="materials")


class MasterySnapshot(Base):
    """Append-only mastery history for time-series mastery curves."""

    __tablename__ = "mastery_snapshots"

    __table_args__ = (
        Index("ix_mastery_snapshots_user_node", "user_id", "node_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    p_known: Mapped[float] = mapped_column(Float, nullable=False)
    p_t: Mapped[float] = mapped_column(Float, nullable=False, default=0.1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VideoProgress(Base):
    """Per-user video watch progress (position + cumulative watched seconds)."""

    __tablename__ = "video_progress"

    __table_args__ = (
        UniqueConstraint("user_id", "video_id", name="uq_video_progress_user_video"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    video_id: Mapped[str] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    position_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    watched_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_watched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
