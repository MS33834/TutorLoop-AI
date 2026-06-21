"""Learning report generation service."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.db.postgres import AsyncSessionLocal
from app.models.db import Course, Interaction, KnowledgeNode
from app.services import bkt_engine

logger = logging.getLogger(__name__)


async def generate_report(user_id: str, course_id: str) -> dict:
    """Generate a learning report for a user in a course."""
    mastery_records = await bkt_engine.get_mastery(user_id, course_id)

    async with AsyncSessionLocal() as session:
        course_result = await session.execute(
            select(Course).where(Course.id == course_id)
        )
        course = course_result.scalar_one_or_none()
        course_title = course.title if course else ""

        total_nodes_result = await session.execute(
            select(func.count(KnowledgeNode.id)).where(KnowledgeNode.course_id == course_id)
        )
        total_nodes = total_nodes_result.scalar() or 0

        interactions_result = await session.execute(
            select(
                func.count(Interaction.id),
                func.coalesce(func.sum(Interaction.watch_seconds), 0.0),
                func.coalesce(func.sum(Interaction.help_count), 0),
            ).where(
                Interaction.user_id == user_id,
                Interaction.course_id == course_id,
            )
        )
        row = interactions_result.one()
        interaction_count = row[0] or 0
        total_watch_seconds = float(row[1] or 0)
        total_help_count = int(row[2] or 0)

        # Correct / incorrect counts
        correct_result = await session.execute(
            select(func.count(Interaction.id)).where(
                Interaction.user_id == user_id,
                Interaction.course_id == course_id,
                Interaction.is_correct == True,  # noqa: E712
            )
        )
        correct_count = correct_result.scalar() or 0

        incorrect_result = await session.execute(
            select(func.count(Interaction.id)).where(
                Interaction.user_id == user_id,
                Interaction.course_id == course_id,
                Interaction.is_correct == False,  # noqa: E712
            )
        )
        incorrect_count = incorrect_result.scalar() or 0

        # Recent 7 days activity
        since = datetime.now(timezone.utc) - timedelta(days=7)
        recent_result = await session.execute(
            select(func.count(Interaction.id)).where(
                Interaction.user_id == user_id,
                Interaction.course_id == course_id,
                Interaction.created_at >= since,
            )
        )
        recent_interactions = recent_result.scalar() or 0

    mastered_count = sum(
        1 for r in mastery_records if r["p_known"] >= r["threshold"]
    )
    weak_nodes = [
        {
            "node_id": r["node_id"],
            "name": r["name"],
            "p_known": r["p_known"],
            "threshold": r["threshold"],
            "gap": round(r["threshold"] - r["p_known"], 3),
        }
        for r in mastery_records
        if r["p_known"] < r["threshold"]
    ]
    weak_nodes.sort(key=lambda x: x["gap"], reverse=True)

    avg_mastery = (
        sum(r["p_known"] for r in mastery_records) / len(mastery_records)
        if mastery_records
        else 0.0
    )

    total_answered = correct_count + incorrect_count
    accuracy = correct_count / total_answered if total_answered > 0 else 0.0

    return {
        "user_id": user_id,
        "course_id": course_id,
        "course_title": course_title,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_nodes": total_nodes,
            "mastered_nodes": mastered_count,
            "mastery_rate": round(mastered_count / total_nodes, 3) if total_nodes else 0.0,
            "average_mastery": round(avg_mastery, 3),
            "interaction_count": interaction_count,
            "recent_7d_interactions": recent_interactions,
            "total_watch_minutes": round(total_watch_seconds / 60, 1),
            "total_help_count": total_help_count,
            "correct_count": correct_count,
            "incorrect_count": incorrect_count,
            "accuracy": round(accuracy, 3),
        },
        "mastery_items": mastery_records,
        "weak_nodes": weak_nodes[:10],
    }
