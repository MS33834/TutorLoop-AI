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
from app.models.db import Room, RoomEntrySession, User
from app.schemas import ChatRequest, HealthResponse, KeyHealthSummary
from app.services import bkt_engine
from app.services.auth_service import get_optional_current_user
from app.services.rag_service import retrieve_context
from app.services.socratic_agent import assess_answer, build_socratic_messages, looks_like_answer

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


async def _resolve_room_for_authenticated(
    room_slug: str | None,
    current_user: User,
    password: str | None,
    session_id: str | None,
) -> Room | None:
    """Validate room slug for an authenticated user, enforcing password/ownership."""
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

        # Owners and admins bypass the password check.
        is_owner_or_admin = (
            room.created_by == current_user.id or current_user.role == "admin"
        )
        if not is_owner_or_admin and room.password_hash:
            # Accept an already-joined session as proof of access.
            has_valid_session = False
            if session_id:
                session_result = await session.execute(
                    select(RoomEntrySession).where(
                        RoomEntrySession.room_id == room.id,
                        RoomEntrySession.session_id == session_id,
                    )
                )
                has_valid_session = session_result.scalar_one_or_none() is not None

            if not has_valid_session:
                from app.services.auth_service import verify_password

                if not password:
                    raise HTTPException(status_code=403, detail="该房间需要密码")
                if not verify_password(password, room.password_hash):
                    raise HTTPException(status_code=403, detail="房间密码错误")

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
        fd, path = tempfile.mkstemp(prefix="chat_screenshot_", suffix=suffix)
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
    if ctx.get("materials"):
        lines.append("相关课程资料：")
        for material in ctx["materials"]:
            lines.append(f"- {material['title']}（{material['file_type']}）：{material['text']}")
    return "\n".join(lines)


async def _record_mastery_after_chat(
    user_id: str | None,
    course_id: str | None,
    video_id: str | None,
    node_id: str | None,
    node_name: str | None,
    context_text: str | None,
    student_answer: str | None,
    request: ChatRequest,
) -> None:
    """Best-effort assessment and BKT update after a Socratic turn.

    Runs after the SSE stream so the user is never blocked by the extra LLM
    call. Failures are logged and swallowed to avoid breaking the chat flow.
    """
    if not user_id or not course_id or not node_id:
        return
    if not student_answer or not looks_like_answer(student_answer):
        return

    # The question the student is answering is the previous assistant turn in
    # the request history (the latest user message is the student's answer).
    previous_question = None
    for msg in reversed(request.messages[:-1] if request.messages else []):
        if getattr(msg, "role", None) == "assistant" and getattr(msg, "content", ""):
            previous_question = msg.content
            break

    try:
        assessment = await assess_answer(
            question_context=context_text or node_name or "",
            student_answer=student_answer,
            node_name=node_name,
            question=previous_question,
        )
    except Exception as exc:
        logger.warning("Answer assessment failed: %s", exc)
        return

    is_correct = assessment.get("is_correct")
    if is_correct is None:
        return

    try:
        await bkt_engine.record_interaction(
            user_id=user_id,
            course_id=course_id,
            video_id=video_id,
            video_timestamp=request.timestamp,
            question_text=previous_question,
            answer_text=student_answer,
            is_correct=is_correct,
            node_id=node_id,
        )
        await bkt_engine.update_mastery(
            user_id=user_id,
            node_id=node_id,
            is_correct=is_correct,
        )
        logger.info(
            "Updated mastery for user=%s node=%s is_correct=%s",
            user_id,
            node_id,
            is_correct,
        )
    except Exception as exc:
        logger.warning("Mastery update after chat failed: %s", exc)


async def _sse_event_stream(request: ChatRequest, user_id: str | None, course_id: str | None):
    messages = [m.model_dump() for m in request.messages]
    context_text: str | None = None
    node_name: str | None = None
    node_id: str | None = None
    screenshot_path: str | None = None
    has_screenshot = False
    student_answer: str | None = None

    if request.messages:
        last_msg = request.messages[-1]
        if last_msg.role == "user":
            student_answer = last_msg.content

    if request.video_id and (request.screenshot or request.timestamp is not None):
        screenshot_path = _save_screenshot_if_any(request.screenshot)
        has_screenshot = screenshot_path is not None
        try:
            ctx = await retrieve_context(
                video_id=request.video_id,
                question=request.messages[-1].content if request.messages else "",
                screenshot_path=screenshot_path,
                timestamp=request.timestamp,
            )
            context_text = _format_context(ctx)
            # Use the top knowledge node (if any) to adapt the Socratic prompt.
            nodes = ctx.get("knowledge_nodes") or []
            if nodes:
                node_id = nodes[0].get("id")
                node_name = nodes[0].get("name")
        except Exception as exc:
            logger.warning("RAG context retrieval failed: %s", exc)
        # NOTE: screenshot_path is NOT deleted here when has_screenshot is
        # True, because it must survive until the VLM request completes.
        # It is deleted after streaming finishes (or on error) below.

    if request.need_answer:
        # Fallback mode: give a direct, concise answer instead of continuing the
        # Socratic dialogue. This prevents students from getting stuck after
        # multiple failed attempts.
        direct_system_prompt = (
            "你是一位耐心的辅导老师。学生已经尝试过思考但仍无法理解，"
            "请直接给出清晰、完整的答案，并附上关键步骤或原理说明。"
        )
        if context_text:
            direct_system_prompt = f"{direct_system_prompt}\n\n{context_text}"
        socratic_messages = [
            {"role": "system", "content": direct_system_prompt},
            *messages,
        ]
    else:
        # Wrap the user messages with a Socratic system prompt adapted to the
        # student's current mastery on the relevant knowledge node.
        socratic_messages = await build_socratic_messages(
            messages=messages,
            user_id=user_id,
            course_id=course_id,
            node_id=node_id,
            context_text=context_text,
            node_name=node_name,
        )

    # When a screenshot is present, route to the vision model and attach the
    # screenshot as an image content block on the latest user message so the
    # VLM can actually "see" what the student is asking about.
    model_type = "vision" if has_screenshot else "text"
    if has_screenshot and screenshot_path and socratic_messages:
        last = socratic_messages[-1]
        if last.get("role") == "user":
            last["content"] = [
                {"type": "text", "text": last.get("content", "")},
                {"type": "image_path", "path": screenshot_path},
            ]

    try:
        async for chunk in stream_chat(socratic_messages, model_type=model_type):
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

        # After the stream finishes, assess the student's answer and update
        # mastery when in Socratic mode. This only runs when no exception
        # interrupted the response.
        if not request.need_answer:
            await _record_mastery_after_chat(
                user_id=user_id,
                course_id=course_id,
                video_id=request.video_id,
                node_id=node_id,
                node_name=node_name,
                context_text=context_text,
                student_answer=student_answer,
                request=request,
            )
    finally:
        # Clean up the screenshot temp file now that streaming is done.
        if screenshot_path:
            try:
                Path(screenshot_path).unlink(missing_ok=True)
            except Exception as exc:
                logger.warning("Could not delete screenshot %s: %s", screenshot_path, exc)


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

    user_id = current_user.id if current_user else None
    course_id: str | None = None

    # Anonymous users must provide a room slug pointing to an anonymous-enabled room.
    if current_user is None:
        room = await _resolve_room_for_anonymous(body.room_slug)
        if room is not None:
            course_id = room.course_id
    else:
        # Resolve course_id from the room slug for authenticated users too,
        # so the Socratic agent can look up mastery. This enforces the same
        # password / expiry / ownership checks as join_room, preventing an
        # authenticated user from bypassing room password protection.
        room = await _resolve_room_for_authenticated(
            body.room_slug,
            current_user,
            body.room_password,
            body.session_id,
        )
        if room is not None:
            course_id = room.course_id

    return StreamingResponse(
        _sse_event_stream(body, user_id, course_id),
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
