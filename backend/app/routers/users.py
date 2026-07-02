"""User mastery, interactions, and recommendation endpoints."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.postgres import AsyncSessionLocal
from app.limiter import limiter
from app.models.db import Interaction, KnowledgeNode, Room, User, VideoProgress
from app.schemas import (
    InteractionCreate,
    InteractionResponse,
    MasteryItem,
    RecommendationResponse,
    ReportResponse,
    VideoProgressUpdate,
)
from app.services import bkt_engine, recommendation, report_service
from app.services.auth_service import (
    get_current_active_user,
    get_optional_current_user,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Best-effort import of MasterySnapshot. The table is added by another
# developer (db.py); if it is not present yet we fall back to the snapshot
# logic in mastery_curve. Importing defensively keeps this router loadable
# even when the model has not landed.
try:
    from app.models.db import MasterySnapshot  # type: ignore
except ImportError:  # pragma: no cover - depends on sibling work landing
    MasterySnapshot = None  # type: ignore[assignment]


async def _require_room_for_anonymous(room_id: str | None) -> Room | None:
    """Ensure the room exists and allows anonymous access when no user is logged in."""
    if not room_id:
        return None
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Room).where(Room.id == room_id, Room.is_active == True)  # noqa: E712
        )
        room = result.scalar_one_or_none()
        if room is None:
            raise HTTPException(status_code=404, detail="房间不存在或已关闭")
        if room.expires_at and room.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="房间已过期")
        if room.password_hash:
            raise HTTPException(
                status_code=403, detail="该房间已加密，匿名用户无法提交记录"
            )
        return room


@router.post("/api/interactions", response_model=InteractionResponse)
@limiter.limit("30/minute")
async def create_interaction(
    body: InteractionCreate,
    request: Request,
    current_user: User | None = Depends(get_optional_current_user),
):
    if not body.course_id:
        raise HTTPException(
            status_code=422, detail="缺少课程 ID"
        )

    effective_user_id = current_user.id if current_user else None

    if current_user is not None:
        if body.user_id and body.user_id != current_user.id:
            raise HTTPException(
                status_code=403, detail="不能为其他用户提交交互记录"
            )
    else:
        # Anonymous interactions must be tied to a room that allows anonymous access.
        room = await _require_room_for_anonymous(body.room_id)
        if room and not room.allow_anonymous:
            raise HTTPException(status_code=401, detail="该房间需要登录后才能提交记录")

    interaction = await bkt_engine.record_interaction(
        user_id=effective_user_id,
        course_id=body.course_id,
        video_id=body.video_id,
        video_timestamp=body.video_timestamp,
        question_text=body.question_text,
        answer_text=body.answer_text,
        is_correct=body.is_correct,
        help_count=body.help_count,
        watch_seconds=body.watch_seconds,
        node_id=body.node_id,
        room_id=body.room_id,
    )

    # Only update mastery for authenticated users.
    mastery_updated = False
    if (
        effective_user_id is not None
        and body.node_id is not None
        and body.is_correct is not None
    ):
        try:
            await bkt_engine.update_mastery(
                user_id=effective_user_id,
                node_id=body.node_id,
                is_correct=body.is_correct,
            )
            mastery_updated = True
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(
                "Mastery update failed for user=%s node=%s: %s",
                effective_user_id,
                body.node_id,
                exc,
            )

    result = InteractionResponse(**interaction, mastery_updated=mastery_updated)
    return result


@router.get("/api/users/me/mastery", response_model=list[MasteryItem])
async def get_my_mastery(
    course_id: str = Query(..., description="Course ID"),
    current_user: User = Depends(get_current_active_user),
):
    if not course_id:
        raise HTTPException(status_code=422, detail="缺少课程 ID")

    return await bkt_engine.get_mastery(current_user.id, course_id)


@router.get("/api/users/me/recommend", response_model=RecommendationResponse)
async def recommend_for_me(
    course_id: str = Query(..., description="Course ID"),
    current_user: User = Depends(get_current_active_user),
):
    if not course_id:
        raise HTTPException(status_code=422, detail="缺少课程 ID")

    try:
        rec = await recommendation.recommend_next(current_user.id, course_id)
    except Exception as exc:
        logger.warning("Recommendation failed: %s", exc)
        return RecommendationResponse(
            recommendation=None,
            message="推荐服务暂时不可用，请稍后重试。",
        )

    if rec is None:
        return RecommendationResponse(
            recommendation=None,
            message="暂时没有合适的下一步推荐，可能你已全部掌握，或还有先修知识需要巩固。",
        )

    return RecommendationResponse(recommendation=rec)


@router.get("/api/users/me/report", response_model=ReportResponse)
async def report_for_me(
    course_id: str = Query(..., description="Course ID"),
    current_user: User = Depends(get_current_active_user),
):
    if not course_id:
        raise HTTPException(status_code=422, detail="缺少课程 ID")

    try:
        return await report_service.generate_report(current_user.id, course_id)
    except Exception as exc:
        logger.warning("Report generation failed: %s", exc)
        raise HTTPException(
            status_code=503, detail="报告生成失败，请稍后重试。"
        ) from exc


@router.get("/api/users/me/timeline")
async def get_my_timeline(
    course_id: str = Query(..., description="Course ID"),
    days: int = Query(30, ge=7, le=90),
    current_user: User = Depends(get_current_active_user),
):
    """Return daily activity and mastery trend data for time-series visualizations."""
    if not course_id:
        raise HTTPException(status_code=422, detail="缺少课程 ID")

    since = datetime.now(timezone.utc) - timedelta(days=days)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Interaction)
            .where(
                Interaction.user_id == current_user.id,
                Interaction.course_id == course_id,
                Interaction.created_at >= since,
            )
            .order_by(Interaction.created_at)
        )
        interactions = result.scalars().all()

    daily = {}
    weekly_correct = {}
    weekly_total = {}
    for i in interactions:
        day = i.created_at.date().isoformat()
        bucket = daily.setdefault(
            day, {"date": day, "count": 0, "watch_minutes": 0.0, "correct": 0, "incorrect": 0}
        )
        bucket["count"] += 1
        bucket["watch_minutes"] += (i.watch_seconds or 0) / 60
        if i.is_correct is True:
            bucket["correct"] += 1
        elif i.is_correct is False:
            bucket["incorrect"] += 1

        # ISO week numbering (%G year + %V week) so a week spanning a year
        # boundary is reported consistently (e.g. 2025-W01) instead of being
        # split across %Y-W%W which uses Sunday-based week 00 for partial weeks.
        week = i.created_at.strftime("%G-W%V")
        weekly_total[week] = weekly_total.get(week, 0) + 1
        if i.is_correct is True:
            weekly_correct[week] = weekly_correct.get(week, 0) + 1

    # Fill missing days with zeros so the heatmap is continuous.
    all_days = []
    for offset in range(days):
        d = (datetime.now(timezone.utc) - timedelta(days=offset)).date().isoformat()
        all_days.append(d)
    all_days.reverse()

    empty_day = {"date": "", "count": 0, "watch_minutes": 0.0, "correct": 0, "incorrect": 0}
    daily_activity = []
    for d in all_days:
        day = daily.get(d, {**empty_day, "date": d})
        daily_activity.append(day)

    weekly_accuracy = [
        {
            "week": week,
            "accuracy": round(weekly_correct.get(week, 0) / total, 3) if total else 0.0,
            "total": total,
        }
        for week, total in sorted(weekly_total.items())
    ]

    mastery_records = await bkt_engine.get_mastery(current_user.id, course_id)
    mastery_curve = await _build_mastery_curve(
        current_user.id, course_id, mastery_records
    )

    return {
        "course_id": course_id,
        "days": days,
        "daily_activity": daily_activity,
        "weekly_accuracy": weekly_accuracy,
        "mastery_curve": mastery_curve,
    }


async def _build_mastery_curve(
    user_id: str,
    course_id: str,
    mastery_records: list[dict],
) -> list[dict]:
    """Return a per-node mastery time-series, falling back to a snapshot.

    The primary path queries MasterySnapshot (written by the BKT engine on
    every update) so the UI can render an actual learning curve over time.
    If MasterySnapshot is not available (model not yet defined in db.py, or
    the underlying table missing) we fall back to the current snapshot from
    ``bkt_engine.get_mastery`` and emit a single-point history so the API
    shape stays consistent for the frontend.
    """
    if MasterySnapshot is not None:
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(
                        MasterySnapshot.node_id,
                        MasterySnapshot.p_known,
                        MasterySnapshot.created_at,
                        KnowledgeNode.name,
                    )
                    .join(
                        KnowledgeNode,
                        KnowledgeNode.id == MasterySnapshot.node_id,
                    )
                    .where(
                        MasterySnapshot.user_id == user_id,
                        KnowledgeNode.course_id == course_id,
                    )
                    .order_by(MasterySnapshot.node_id, MasterySnapshot.created_at)
                )
                rows = result.all()

            if rows:
                grouped: dict[str, dict] = {}
                for node_id, p_known, created_at, node_name in rows:
                    bucket = grouped.setdefault(
                        node_id,
                        {"node_id": node_id, "node_name": node_name, "history": []},
                    )
                    bucket["history"].append(
                        {
                            "timestamp": created_at.isoformat() if created_at else None,
                            "p_known": round(float(p_known), 3) if p_known is not None else 0.0,
                        }
                    )
                return list(grouped.values())
        except Exception as exc:
            # Missing table, schema drift, or any other DB error: fall back
            # to the snapshot so the timeline endpoint still works.
            logger.warning(
                "MasterySnapshot query failed, falling back to snapshot: %s", exc
            )

    # Fallback: one history point per node representing the current p_known.
    return [
        {
            "node_id": r["node_id"],
            "node_name": r.get("name"),
            "history": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "p_known": round(r["p_known"], 3),
                }
            ],
        }
        for r in mastery_records
    ]


@router.get("/api/users/me/interactions", response_model=list[InteractionResponse])
async def list_my_interactions(
    course_id: str = Query(..., description="Course ID"),
    node_id: str | None = Query(None, description="Optional knowledge node ID filter"),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
):
    """Return the current user's recent interactions for a course/node."""
    if not course_id:
        raise HTTPException(status_code=422, detail="缺少课程 ID")

    async with AsyncSessionLocal() as session:
        stmt = (
            select(Interaction)
            .where(
                Interaction.user_id == current_user.id,
                Interaction.course_id == course_id,
            )
            .order_by(Interaction.created_at.desc())
            .limit(limit)
        )
        if node_id:
            stmt = stmt.where(Interaction.node_id == node_id)

        result = await session.execute(stmt)
        interactions = result.scalars().all()

    return [
        InteractionResponse(
            id=i.id,
            user_id=i.user_id,
            room_id=i.room_id,
            course_id=i.course_id,
            video_id=i.video_id,
            video_timestamp=i.video_timestamp,
            question_text=i.question_text,
            answer_text=i.answer_text,
            is_correct=i.is_correct,
            help_count=i.help_count,
            watch_seconds=i.watch_seconds,
            node_id=i.node_id,
            created_at=i.created_at.isoformat(),
        )
        for i in interactions
    ]


# Question-type categorization rules. Order matters: the first matching rule
# wins. Troubleshooting is checked first because an error report containing
# "why" should still be classified as troubleshooting, not inquiry. The
# categories align with common pedagogical taxonomies (conceptual /
# procedural / inquiry / troubleshooting) and the frontend's chart labels.
_QUESTION_CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    ("troubleshooting", ("错误", "报错", "error", "bug", "异常", "失败", "crash")),
    ("procedural", ("怎么做", "如何", "怎么", "步骤", "how to", "how do", "how does")),
    ("inquiry", ("为什么", "为何", "原因", "why", "why not", "why does")),
    ("conceptual", ("是什么", "什么是", "什么意思", "区别", "定义", "what is", "what are", "concept")),
]


def _classify_question(text: str | None) -> str:
    """Return the question category for a piece of text, or 'other'."""
    if not text:
        return "other"
    lowered = text.lower()
    for category, keywords in _QUESTION_CATEGORIES:
        for kw in keywords:
            if kw in lowered:
                return category
    return "other"


@router.get("/api/users/me/question-distribution")
async def get_my_question_distribution(
    course_id: str | None = Query(None, description="Optional course ID filter"),
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_active_user),
):
    """Return the distribution of the user's question types.

    Questions are classified by keyword heuristics into conceptual /
    procedural / inquiry / troubleshooting / other. The response is suitable
    for a pie/donut chart on the learner dashboard.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    async with AsyncSessionLocal() as session:
        stmt = (
            select(Interaction.question_text)
            .where(
                Interaction.user_id == current_user.id,
                Interaction.created_at >= since,
            )
        )
        if course_id:
            stmt = stmt.where(Interaction.course_id == course_id)
        result = await session.execute(stmt)
        question_texts = [row[0] for row in result.all()]

    counts: dict[str, int] = {
        "conceptual": 0,
        "procedural": 0,
        "inquiry": 0,
        "troubleshooting": 0,
        "other": 0,
    }
    for text in question_texts:
        counts[_classify_question(text)] += 1

    total = sum(counts.values())
    distribution = [
        {
            "category": category,
            "count": count,
            "percentage": round(count / total, 3) if total else 0.0,
        }
        for category, count in counts.items()
    ]
    return {
        "total": total,
        "days": days,
        "course_id": course_id,
        "distribution": distribution,
    }


# ---------------------------------------------------------------------------
# Video progress sync (PRD 2.2 – 时间轴进度与后端同步)
# ---------------------------------------------------------------------------

@router.put("/api/users/me/videos/{video_id}/progress")
async def save_video_progress(
    video_id: str,
    payload: VideoProgressUpdate,
    current_user: User = Depends(get_current_active_user),
):
    """Upsert the user's playback position for a video.

    Called periodically by the frontend VideoPlayer to support resume-playback
    and watching-time analytics.
    """
    async with AsyncSessionLocal() as session:
        stmt = (
            pg_insert(VideoProgress)
            .values(
                user_id=current_user.id,
                video_id=video_id,
                position_seconds=payload.position_seconds,
                watched_seconds=payload.watched_seconds,
            )
            .on_conflict_do_update(
                index_elements=["user_id", "video_id"],
                set_={
                    "position_seconds": payload.position_seconds,
                    "watched_seconds": payload.watched_seconds,
                    "last_watched_at": datetime.now(timezone.utc),
                },
            )
        )
        await session.execute(stmt)
        await session.commit()
    return {"status": "ok"}


@router.get("/api/users/me/videos/{video_id}/progress")
async def get_video_progress(
    video_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """Retrieve the user's last playback position for a video."""
    async with AsyncSessionLocal() as session:
        row = await session.execute(
            select(VideoProgress).where(
                VideoProgress.user_id == current_user.id,
                VideoProgress.video_id == video_id,
            )
        )
        progress = row.scalar_one_or_none()
    if progress is None:
        return {"position_seconds": 0.0, "watched_seconds": 0.0, "last_watched_at": None}
    return {
        "position_seconds": progress.position_seconds,
        "watched_seconds": progress.watched_seconds,
        "last_watched_at": progress.last_watched_at.isoformat() if progress.last_watched_at else None,
    }
