"""User mastery, interactions, and recommendation endpoints."""

import logging

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.db.postgres import AsyncSessionLocal
from app.models.db import Room, User
from app.schemas import (
    InteractionCreate,
    InteractionResponse,
    MasteryItem,
    RecommendationResponse,
    ReportResponse,
)
from app.services import bkt_engine, recommendation, report_service
from app.services.auth_service import (
    get_current_active_user,
    get_optional_current_user,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def _require_room_for_anonymous(room_id: str | None) -> Room | None:
    """Ensure the room exists and allows anonymous access when no user is logged in."""
    if not room_id:
        return None
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Room).where(Room.id == room_id, Room.is_active == True)
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
async def create_interaction(
    body: InteractionCreate,
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
            logger.error("Mastery update failed for user=%s node=%s: %s", effective_user_id, body.node_id, exc)

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
