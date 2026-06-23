"""Class-level learning analytics for teacher dashboards."""

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import Float, cast, func, select

from app.db.postgres import AsyncSessionLocal
from app.models.db import Interaction, KnowledgeNode, Mastery, User

logger = logging.getLogger(__name__)


def _format_date(value: datetime | date) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


def _fill_activity_trend(rows: list[tuple[datetime | date, int]]) -> list[dict[str, str | int]]:
    """Convert raw daily counts into a complete 7-day trend ending today."""
    counts = {}
    for day_value, count in rows:
        counts[_format_date(day_value)] = count or 0

    trend = []
    today = date.today()
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        trend.append({"date": day.isoformat(), "count": counts.get(day.isoformat(), 0)})
    return trend


def _aggregate_weak_nodes(
    rows: list[tuple[str, float, str, str, float]],
) -> list[dict]:
    """Aggregate mastery rows into weak nodes ranked by average gap.

    Each input row is (user_id, p_known, node_id, node_name, threshold).
    """
    stats: dict[str, dict] = defaultdict(lambda: {"p_knowns": [], "below": 0})

    for _user_id, p_known, node_id, node_name, threshold in rows:
        node = stats[node_id]
        node["name"] = node_name
        node["threshold"] = threshold
        node["p_knowns"].append(p_known)
        if p_known < threshold:
            node["below"] += 1

    weak_nodes = []
    for node_id, data in stats.items():
        p_knowns = data["p_knowns"]
        avg_p = sum(p_knowns) / len(p_knowns) if p_knowns else 0.0
        threshold = data["threshold"]
        if avg_p < threshold:
            gap = round(threshold - avg_p, 3)
            weak_nodes.append(
                {
                    "node_id": node_id,
                    "name": data["name"],
                    "avg_p_known": round(avg_p, 3),
                    "threshold": threshold,
                    "gap": gap,
                    "struggling_students": data["below"],
                }
            )

    weak_nodes.sort(key=lambda x: x["gap"], reverse=True)
    return weak_nodes


def _class_avg_mastery(rows: list[tuple[str, float, str, str, float]]) -> float:
    values = [p for _, p, _, _, _ in rows]
    return round(sum(values) / len(values), 3) if values else 0.0


async def generate_class_report(course_id: str) -> dict:
    """Generate an aggregated class report for a course.

    Includes student summaries, weak knowledge nodes, and 7-day activity trend.
    """
    async with AsyncSessionLocal() as session:
        student_count_result = await session.execute(
            select(func.count(func.distinct(Interaction.user_id))).where(
                Interaction.course_id == course_id,
                Interaction.user_id.isnot(None),
            )
        )
        total_students = student_count_result.scalar() or 0

        summary_result = await session.execute(
            select(
                func.count(Interaction.id),
                func.coalesce(func.sum(Interaction.watch_seconds), 0.0),
                func.coalesce(func.sum(Interaction.help_count), 0),
            ).where(Interaction.course_id == course_id)
        )
        total_interactions, total_watch_seconds, total_help_count = summary_result.one()
        total_interactions = total_interactions or 0
        total_watch_minutes = round(float(total_watch_seconds or 0) / 60, 1)
        total_help_count = int(total_help_count or 0)

        correct_result = await session.execute(
            select(func.count(Interaction.id)).where(
                Interaction.course_id == course_id,
                Interaction.is_correct == True,  # noqa: E712
            )
        )
        correct_count = correct_result.scalar() or 0

        incorrect_result = await session.execute(
            select(func.count(Interaction.id)).where(
                Interaction.course_id == course_id,
                Interaction.is_correct == False,  # noqa: E712
            )
        )
        incorrect_count = incorrect_result.scalar() or 0

        total_answered = correct_count + incorrect_count
        accuracy = round(correct_count / total_answered, 3) if total_answered else 0.0

        since = datetime.now(timezone.utc) - timedelta(days=7)
        student_rows = await session.execute(
            select(
                Interaction.user_id,
                User.username,
                func.count(Interaction.id).label("interaction_count"),
                func.coalesce(func.sum(Interaction.watch_seconds), 0.0).label("watch_seconds"),
                func.coalesce(
                    func.avg(cast(Interaction.is_correct, Float)), 0.0
                ).label("accuracy"),
                func.max(Interaction.created_at).label("last_active_at"),
            )
            .outerjoin(User, Interaction.user_id == User.id)
            .where(
                Interaction.course_id == course_id,
                Interaction.user_id.isnot(None),
                Interaction.is_correct.isnot(None),
            )
            .group_by(Interaction.user_id, User.username)
            .order_by(func.max(Interaction.created_at).desc())
        )

        mastery_rows = await session.execute(
            select(
                Mastery.user_id,
                Mastery.p_known,
                Mastery.node_id,
                KnowledgeNode.name,
                KnowledgeNode.threshold,
            )
            .join(KnowledgeNode)
            .where(KnowledgeNode.course_id == course_id)
        )
        mastery_list = list(mastery_rows.all())

        activity_rows = await session.execute(
            select(
                func.date_trunc("day", Interaction.created_at).label("day"),
                func.count(Interaction.id).label("count"),
            )
            .where(
                Interaction.course_id == course_id,
                Interaction.created_at >= since,
            )
            .group_by("day")
            .order_by("day")
        )

    class_avg_mastery = _class_avg_mastery(mastery_list)
    mastery_by_user: dict[str, list[float]] = defaultdict(list)
    for user_id, p_known, *_rest in mastery_list:
        mastery_by_user[user_id].append(p_known)

    students = []
    for row in student_rows.all():
        user_id, username, interaction_count, watch_seconds, acc, last_active_at = row
        user_mastery = mastery_by_user.get(user_id, [])
        avg_mastery = round(sum(user_mastery) / len(user_mastery), 3) if user_mastery else 0.0
        students.append(
            {
                "user_id": user_id,
                "username": username or "匿名学生",
                "interaction_count": interaction_count or 0,
                "watch_minutes": round(float(watch_seconds or 0) / 60, 1),
                "accuracy": round(float(acc or 0), 3),
                "avg_mastery": avg_mastery,
                "last_active_at": last_active_at.isoformat() if last_active_at else None,
            }
        )

    return {
        "course_id": course_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_students": total_students,
            "total_interactions": total_interactions,
            "total_watch_minutes": total_watch_minutes,
            "total_help_count": total_help_count,
            "correct_count": correct_count,
            "incorrect_count": incorrect_count,
            "accuracy": accuracy,
            "class_avg_mastery": class_avg_mastery,
        },
        "students": students,
        "weak_nodes": _aggregate_weak_nodes(mastery_list),
        "activity_trend": _fill_activity_trend(activity_rows.all()),
    }
