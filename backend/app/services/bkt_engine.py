"""Bayesian Knowledge Tracing mastery engine."""

import logging
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.postgres import AsyncSessionLocal
from app.models.db import Interaction, KnowledgeNode, Mastery

logger = logging.getLogger(__name__)


def _p_l0() -> float:
    return settings.bkt_p_l0


def _p_t() -> float:
    return settings.bkt_p_t


def _p_g() -> float:
    return settings.bkt_p_g


def _p_s() -> float:
    return settings.bkt_p_s


def _bkt_update(p_l: float, is_correct: bool, p_g: float, p_s: float) -> float:
    """Apply BKT observation update and learning transition."""
    if is_correct:
        numerator = p_l * (1 - p_s)
        denominator = p_l * (1 - p_s) + (1 - p_l) * p_g
    else:
        numerator = p_l * p_s
        denominator = p_l * p_s + (1 - p_l) * (1 - p_g)

    denominator = denominator or 1e-9
    p_l_given_obs = numerator / denominator
    p_l_next = p_l_given_obs + (1 - p_l_given_obs) * _p_t()
    return max(0.0, min(1.0, p_l_next))


async def initialize_mastery(user_id: str, course_id: str) -> None:
    """Create initial Mastery records for a user in a course."""
    async with AsyncSessionLocal() as session:
        node_result = await session.execute(
            select(KnowledgeNode).where(KnowledgeNode.course_id == course_id)
        )
        nodes = node_result.scalars().all()

        for node in nodes:
            existing = await session.get(Mastery, {"user_id": user_id, "node_id": node.id})
            if existing is None:
                session.add(
                    Mastery(
                        user_id=user_id,
                        node_id=node.id,
                        p_known=_p_l0(),
                        p_t=_p_t(),
                        interactions_count=0,
                    )
                )

        await session.commit()


async def update_mastery(user_id: str, node_id: str, is_correct: bool) -> dict:
    """Update mastery for a user/node after one interaction."""
    async with AsyncSessionLocal() as session:
        mastery = await session.get(Mastery, {"user_id": user_id, "node_id": node_id})
        if mastery is None:
            raise HTTPException(status_code=404, detail="Mastery record not found")

        mastery.p_known = _bkt_update(mastery.p_known, is_correct, _p_g(), _p_s())
        mastery.interactions_count += 1
        mastery.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(mastery)

        return {
            "user_id": mastery.user_id,
            "node_id": mastery.node_id,
            "p_known": mastery.p_known,
            "p_t": mastery.p_t,
            "interactions_count": mastery.interactions_count,
            "updated_at": mastery.updated_at.isoformat(),
        }


async def get_mastery(user_id: str, course_id: str) -> list[dict]:
    """Return mastery records for a user in a course, joined with node info."""
    async with AsyncSessionLocal() as session:
        has_records_result = await session.execute(
            select(Mastery)
            .join(KnowledgeNode)
            .where(
                Mastery.user_id == user_id,
                KnowledgeNode.course_id == course_id,
            )
            .limit(1)
        )
        has_records = has_records_result.scalar_one_or_none() is not None

    if not has_records:
        await initialize_mastery(user_id, course_id)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Mastery)
            .options(selectinload(Mastery.node))
            .join(KnowledgeNode)
            .where(
                Mastery.user_id == user_id,
                KnowledgeNode.course_id == course_id,
            )
            .order_by(KnowledgeNode.created_at)
        )
        records = result.scalars().all()

        return [
            {
                "node_id": record.node_id,
                "name": record.node.name,
                "description": record.node.description,
                "threshold": record.node.threshold,
                "p_known": record.p_known,
                "p_t": record.p_t,
                "interactions_count": record.interactions_count,
            }
            for record in records
        ]


async def record_interaction(
    user_id: str,
    course_id: str,
    video_id: str | None,
    video_timestamp: float | None,
    question_text: str | None,
    answer_text: str | None,
    is_correct: bool | None,
    help_count: int = 0,
    watch_seconds: float | None = None,
    node_id: str | None = None,
    room_id: str | None = None,
) -> dict:
    """Insert a new Interaction record."""
    interaction = Interaction(
        user_id=user_id,
        course_id=course_id,
        video_id=video_id,
        video_timestamp=video_timestamp,
        question_text=question_text,
        answer_text=answer_text,
        is_correct=is_correct,
        help_count=help_count,
        watch_seconds=watch_seconds,
        node_id=node_id,
        room_id=room_id,
    )

    async with AsyncSessionLocal() as session:
        session.add(interaction)
        await session.commit()
        await session.refresh(interaction)

    return {
        "id": interaction.id,
        "user_id": interaction.user_id,
        "course_id": interaction.course_id,
        "video_id": interaction.video_id,
        "video_timestamp": interaction.video_timestamp,
        "question_text": interaction.question_text,
        "answer_text": interaction.answer_text,
        "is_correct": interaction.is_correct,
        "help_count": interaction.help_count,
        "watch_seconds": interaction.watch_seconds,
        "node_id": interaction.node_id,
        "room_id": interaction.room_id,
        "created_at": interaction.created_at.isoformat(),
    }
