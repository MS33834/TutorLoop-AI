"""Bayesian Knowledge Tracing mastery engine."""

import logging
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import insert, select
from sqlalchemy.orm import selectinload
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from app.db.postgres import AsyncSessionLocal
from app.models.db import Interaction, KnowledgeNode, Mastery, MasterySnapshot

logger = logging.getLogger(__name__)

_db_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.1, min=0.1, max=1),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    reraise=True,
)


def _bkt_update(p_l: float, is_correct: bool, p_g: float, p_s: float, p_t: float | None = None) -> float:
    """Apply BKT observation update and learning transition.

    ``p_t`` is the per-node learning (transition) probability. When None it
    falls back to the global ``settings.bkt_p_t`` so callers/tests that don't
    care about per-node tuning keep working.
    """
    if p_t is None:
        p_t = settings.bkt_p_t
    if not (0.0 <= p_l <= 1.0 and 0.0 <= p_g <= 1.0 and 0.0 <= p_s <= 1.0 and 0.0 <= p_t <= 1.0):
        raise ValueError("BKT probabilities must be in [0, 1]")

    if is_correct:
        numerator = p_l * (1 - p_s)
        denominator = p_l * (1 - p_s) + (1 - p_l) * p_g
    else:
        numerator = p_l * p_s
        denominator = p_l * p_s + (1 - p_l) * (1 - p_g)

    denominator = denominator if denominator and denominator > 0 else 1e-9
    p_l_given_obs = numerator / denominator
    p_l_given_obs = max(0.0, min(1.0, p_l_given_obs))
    p_l_next = p_l_given_obs + (1 - p_l_given_obs) * p_t
    return max(0.0, min(1.0, p_l_next))


@_db_retry
async def initialize_mastery(user_id: str, course_id: str) -> None:
    """Create initial Mastery records for a user in a course.

    Uses a single bulk INSERT for all missing nodes instead of per-row
    ``session.add()`` calls, reducing round-trips for courses with many
    knowledge nodes.
    """
    async with AsyncSessionLocal() as session:
        # Batch load all node IDs for the course.
        node_result = await session.execute(
            select(KnowledgeNode.id).where(KnowledgeNode.course_id == course_id)
        )
        all_node_ids = {row[0] for row in node_result.all()}
        if not all_node_ids:
            return

        # Batch load existing mastery records for this user, scoped to the
        # current course via the node join so we don't pull records from other
        # courses the user may be enrolled in.
        existing_result = await session.execute(
            select(Mastery.node_id)
            .join(KnowledgeNode, Mastery.node_id == KnowledgeNode.id)
            .where(Mastery.user_id == user_id, KnowledgeNode.course_id == course_id)
        )
        existing_node_ids = {row[0] for row in existing_result.all()}

        # Bulk insert missing records in a single statement.
        missing = all_node_ids - existing_node_ids
        if missing:
            await session.execute(
                insert(Mastery),
                [
                    {
                        "user_id": user_id,
                        "node_id": node_id,
                        "p_known": settings.bkt_p_l0,
                        "p_t": settings.bkt_p_t,
                        "p_g": settings.bkt_p_g,
                        "p_s": settings.bkt_p_s,
                        "p_l0": settings.bkt_p_l0,
                        "interactions_count": 0,
                    }
                    for node_id in missing
                ],
            )
            await session.commit()


@_db_retry
async def update_mastery(user_id: str, node_id: str, is_correct: bool) -> dict:
    """Update mastery for a user/node after one interaction.

    If no Mastery row exists yet (e.g. new nodes were added to the course after
    the user's last ``initialize_mastery``), lazily initialize the course's
    mastery records so the interaction is never left dangling with a 404.

    ``initialize_mastery`` runs in its own session/transaction so the backfill
    commit does not interfere with this session's pending work. After each
    update a ``MasterySnapshot`` row is appended for time-series mastery curves.
    """
    async with AsyncSessionLocal() as session:
        # Load the mastery row together with its node so we can read
        # ``course_id`` for the snapshot without an extra round-trip and without
        # triggering async lazy-loading (which would raise MissingGreenlet).
        result = await session.execute(
            select(Mastery)
            .options(selectinload(Mastery.node))
            .where(Mastery.user_id == user_id, Mastery.node_id == node_id)
        )
        mastery = result.scalar_one_or_none()

        if mastery is None:
            # Resolve the course from the node and backfill missing records.
            node = await session.get(KnowledgeNode, node_id)
            if node is None:
                raise HTTPException(status_code=404, detail="未找到知识点节点")
            course_id = node.course_id
            # Roll back to clear this session's pending state before the
            # independent initialize_mastery session commits new rows.
            await session.rollback()
            # initialize_mastery opens its own session, so its commit cannot
            # corrupt this session's transaction.
            await initialize_mastery(user_id, course_id)
            result = await session.execute(
                select(Mastery)
                .options(selectinload(Mastery.node))
                .where(Mastery.user_id == user_id, Mastery.node_id == node_id)
            )
            mastery = result.scalar_one_or_none()
            if mastery is None:
                raise HTTPException(status_code=404, detail="未找到掌握度记录")

        course_id = mastery.node.course_id

        # Use per-node BKT parameters when available, falling back to the
        # global settings defaults if a value is missing or zero (which can
        # happen for rows created before the p_g/p_s/p_l0 columns existed).
        p_t = mastery.p_t if mastery.p_t else settings.bkt_p_t
        p_g = mastery.p_g if mastery.p_g else settings.bkt_p_g
        p_s = mastery.p_s if mastery.p_s else settings.bkt_p_s

        new_p_known = _bkt_update(mastery.p_known, is_correct, p_g, p_s, p_t=p_t)
        mastery.p_known = new_p_known
        mastery.p_t = p_t
        mastery.interactions_count += 1
        mastery.updated_at = datetime.now(UTC)

        # Append a mastery history snapshot for time-series analytics.
        snapshot = MasterySnapshot(
            user_id=user_id,
            node_id=node_id,
            course_id=course_id,
            p_known=new_p_known,
            p_t=p_t,
        )
        session.add(snapshot)

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


@_db_retry
async def get_mastery(user_id: str, course_id: str) -> list[dict]:
    """Return mastery records for a user in a course, joined with node info."""
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

        if not records:
            await initialize_mastery(user_id, course_id)
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
                "p_g": record.p_g,
                "p_s": record.p_s,
                "interactions_count": record.interactions_count,
            }
            for record in records
        ]


@_db_retry
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
