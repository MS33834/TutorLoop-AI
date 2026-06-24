"""Chat and health endpoints."""

import base64
import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.db.postgres import AsyncSessionLocal
from app.gateway import pool, stream_chat
from app.limiter import limiter
from app.models.db import Room, User
from app.schemas import ChatRequest, HealthResponse, KeyHealthSummary
from app.services.auth_service import get_optional_current_user
from app.services.rag_service import retrieve_context

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_SCREENSHOT_BYTES = 2 * 1024 * 1024  # 2 MB


async def _resolve_room_for_anonymous(room_slug: str | None) -> Room | None:
    """Validate room slug for anonymous access and return the room."""
    if not room_slug:
        return None
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Room).where(Room.slug == room_slug, Room.is_active == True)  # noqa: E712
        )
        room = result.scalar_one_or_none()
        if room is None:
            raise HTTPException(status_code=404, detail="房间不存在或已关闭")
        if room.expires_at and room.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="房间已过期")
        if room.password_hash:
            raise HTTPException(
                status_code=403, detail="该房间已加密，匿名用户无法访问"
            )
        if not room.allow_anonymous:
            raise HTTPException(status_code=401, detail="该房间需要登录后才能访问")
        return room


def _save_screenshot_if_any(screenshot: str | None) -> str | None:
    """Save a base64 screenshot to a temporary file and return the path."""
    if not screenshot:
        return None
    try:
        header, _, data = screenshot.partition(",")
        image_data = data if data else header
        if not image_data:
            return None
        raw = base64.b64decode(image_data)
        if len(raw) > MAX_SCREENSHOT_BYTES:
            logger.warning("Screenshot too large: %s bytes", len(raw))
            return None
        mime = header.lower()
        if "png" in mime:
            suffix = ".png"
        elif "jpg" in mime or "jpeg" in mime:
            suffix = ".jpg"
        else:
            logger.warning("Unsupported screenshot format: %s", mime)
            return None
        fd, path = tempfile.mkstemp(suffix=suffix)
        with open(fd, "wb") as f:
            f.write(raw)
        return path
    except Exception as exc:
        logger.warning("Could not save screenshot: %s", exc)
        return None


def _format_context(ctx: dict) -> str:
    lines = ["以下是用户当前学习场景的上下文信息："]
    if ctx.get("frames"):
        lines.append("相关视频帧：")
        for frame in ctx["frames"]:
            lines.append(
                f"- 时间 {frame['timestamp_seconds']}s，路径 {frame['file_path']}，"
                f"描述：{frame.get('caption') or '无'}"
            )
    if ctx.get("knowledge_nodes"):
        lines.append("相关知识点：")
        for node in ctx["knowledge_nodes"]:
            lines.append(f"- {node['name']}：{node.get('description') or '无'}")
    if ctx.get("screenshot_path"):
        lines.append(f"用户截图路径：{ctx['screenshot_path']}")
    return "\n".join(lines)


async def _sse_event_stream(request: ChatRequest):
    messages = [m.model_dump() for m in request.messages]

    if request.video_id and (request.screenshot or request.timestamp is not None):
        screenshot_path = _save_screenshot_if_any(request.screenshot)
        try:
            ctx = await retrieve_context(
                video_id=request.video_id,
                question=request.messages[-1].content if request.messages else "",
                screenshot_path=screenshot_path,
                timestamp=request.timestamp,
            )
            context_text = _format_context(ctx)
            messages.insert(0, {"role": "system", "content": context_text})
        except Exception as exc:
            logger.warning("RAG context retrieval failed: %s", exc)
        finally:
            if screenshot_path and Path(screenshot_path).exists():
                Path(screenshot_path).unlink(missing_ok=True)

    async for chunk in stream_chat(messages, model_type="text"):
        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/api/chat")
@limiter.limit("10/minute")
async def chat(
    request: Request,
    body: ChatRequest,
    current_user: User | None = Depends(get_optional_current_user),
):
    if not body.messages:
        raise HTTPException(status_code=422, detail="消息内容不能为空")
    if len(body.messages) > 50:
        raise HTTPException(status_code=422, detail="消息数量超出限制")

    # Anonymous users must provide a room slug pointing to an anonymous-enabled room.
    if current_user is None:
        await _resolve_room_for_anonymous(body.room_slug)

    return StreamingResponse(
        _sse_event_stream(body),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/health", response_model=HealthResponse)
async def health():
    keys = [
        KeyHealthSummary(
            model=k["model"],
            status=k["status"],
            error_count=k["error_count"],
            avg_rtt_ms=k["avg_rtt_ms"],
        )
        for k in pool.summary()
    ]
    overall = "ok" if any(k.status == "healthy" for k in keys) else "degraded"
    return HealthResponse(status=overall, keys=keys)
