"""User mastery, interactions, and recommendation endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Query

from app.schemas import (
    InteractionCreate,
    InteractionResponse,
    MasteryItem,
    RecommendationResponse,
    ReportResponse,
)
from app.services import bkt_engine, recommendation, report_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/interactions", response_model=InteractionResponse)
async def create_interaction(body: InteractionCreate):
    if not body.user_id or not body.course_id:
        raise HTTPException(
            status_code=422, detail="user_id and course_id are required"
        )

    interaction = await bkt_engine.record_interaction(
        user_id=body.user_id,
        course_id=body.course_id,
        video_id=body.video_id,
        video_timestamp=body.video_timestamp,
        question_text=body.question_text,
        answer_text=body.answer_text,
        is_correct=body.is_correct,
        help_count=body.help_count,
        watch_seconds=body.watch_seconds,
        node_id=body.node_id,
    )

    if body.node_id is not None and body.is_correct is not None:
        try:
            await bkt_engine.update_mastery(
                user_id=body.user_id,
                node_id=body.node_id,
                is_correct=body.is_correct,
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Mastery update failed: %s", exc)

    return InteractionResponse(**interaction)


@router.get("/api/users/{user_id}/mastery", response_model=list[MasteryItem])
async def get_user_mastery(
    user_id: str, course_id: str = Query(..., description="Course ID")
):
    if not course_id:
        raise HTTPException(status_code=422, detail="course_id is required")

    return await bkt_engine.get_mastery(user_id, course_id)


@router.get("/api/users/{user_id}/recommend", response_model=RecommendationResponse)
async def recommend_for_user(
    user_id: str, course_id: str = Query(..., description="Course ID")
):
    if not course_id:
        raise HTTPException(status_code=422, detail="course_id is required")

    try:
        rec = await recommendation.recommend_next(user_id, course_id)
    except Exception as exc:
        logger.warning("Recommendation failed: %s", exc)
        return RecommendationResponse(
            recommendation=None,
            message="推荐服务暂时不可用，请稍后重试。",
        )

    if rec is None:
        return RecommendationResponse(
            recommendation=None,
            message="当前没有合适的推荐节点（可能已全部掌握或前置条件未满足）。",
        )

    return RecommendationResponse(recommendation=rec)


@router.get("/api/users/{user_id}/report", response_model=ReportResponse)
async def report_for_user(
    user_id: str, course_id: str = Query(..., description="Course ID")
):
    if not course_id:
        raise HTTPException(status_code=422, detail="course_id is required")

    try:
        return await report_service.generate_report(user_id, course_id)
    except Exception as exc:
        logger.warning("Report generation failed: %s", exc)
        raise HTTPException(
            status_code=503, detail="报告生成失败，请稍后重试。"
        ) from exc
