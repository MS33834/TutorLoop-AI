"""SQLAlchemy ORM models for TutorLoop-AI."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text
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
    embedding = _vector_column()
    created_at: Mapped[datetime] = mapped_column(default=now_utc)

    course: Mapped["Course"] = relationship(back_populates="knowledge_nodes")
    mastery_records: Mapped[list["Mastery"]] = relationship(
        back_populates="node", cascade="all, delete-orphan"
    )


class Mastery(Base):
    __tablename__ = "mastery"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    node_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), primary_key=True
    )
    p_known: Mapped[float] = mapped_column(Float, default=0.3)
    p_t: Mapped[float] = mapped_column(Float, default=0.3)
    interactions_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(default=now_utc)

    node: Mapped["KnowledgeNode"] = relationship(back_populates="mastery_records")


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    room_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    course_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    video_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    node_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    video_timestamp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    screenshot_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    question_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    answer_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_correct: Mapped[Optional[bool]] = mapped_column(nullable=True)
    help_count: Mapped[int] = mapped_column(Integer, default=0)
    watch_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=now_utc)
