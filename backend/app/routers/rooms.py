"""Learning room endpoints for TutorLoop AI."""

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db.postgres import AsyncSessionLocal
from app.limiter import limiter
from app.models.db import Course, Room, RoomEntrySession, User
from app.schemas import (
    RoomCreate,
    RoomJoinRequest,
    RoomPublicResponse,
    RoomResponse,
    RoomUpdate,
)
from app.services.auth_service import (
    get_current_active_user,
    get_password_hash,
    verify_password,
)

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_SLUG_RETRIES = 5


def _generate_slug() -> str:
    """Generate a short URL-safe room slug."""
    return secrets.token_urlsafe(6)[:8]


def _sign_session_id(room_id: str, raw_session: str) -> str:
    """Return an HMAC signature over (room_id, raw_session) using SECRET_KEY.

    The signed session_id format is ``raw_session.signature`` so the server can
    verify a session_id was issued by it (via get_room) and not fabricated by a
    client to bypass participant-count deduplication.
    """
    mac = hmac.new(
        settings.secret_key.encode("utf-8"),
        f"{room_id}:{raw_session}".encode("utf-8"),
        hashlib.sha256,
    )
    return f"{raw_session}.{mac.hex()}"


def _verify_session_id(room_id: str, signed_session: str) -> bool:
    """Verify a server-issued session_id signature. Returns True if valid."""
    if not signed_session or "." not in signed_session:
        return False
    raw_session, _, signature = signed_session.rpartition(".")
    if not raw_session or not signature:
        return False
    expected = _sign_session_id(room_id, raw_session)
    # Use hmac.compare_digest for constant-time comparison.
    return hmac.compare_digest(expected, signed_session)


def _parse_expires_at(value: str | None) -> datetime | None:
    """Parse an ISO-8601 datetime and ensure it is timezone-aware."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"expires_at 格式错误: {exc}") from exc

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _serialize_room(room: Room) -> RoomResponse:
    return RoomResponse(
        id=room.id,
        slug=room.slug,
        course_id=room.course_id,
        title=room.title,
        allow_anonymous=room.allow_anonymous,
        is_active=room.is_active,
        expires_at=room.expires_at.isoformat() if room.expires_at else None,
        entry_count=room.entry_count,
        last_activity_at=room.last_activity_at.isoformat() if room.last_activity_at else None,
        welcome_message=room.welcome_message,
        max_participants=room.max_participants,
        config_json=room.config_json,
        created_at=room.created_at.isoformat(),
    )


def _serialize_public_room(room: Room) -> RoomPublicResponse:
    return RoomPublicResponse(
        id=room.id,
        slug=room.slug,
        course_id=room.course_id,
        title=room.title,
        require_password=bool(room.password_hash),
        allow_anonymous=room.allow_anonymous,
        is_active=room.is_active,
        expires_at=room.expires_at.isoformat() if room.expires_at else None,
    )


async def _require_course_owner(course_id: str, current_user: User) -> Course:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Course).where(Course.id == course_id))
        course = result.scalar_one_or_none()
        if course is None:
            raise HTTPException(status_code=404, detail="课程不存在")
        if course.created_by != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="没有权限操作该课程")
        return course


async def _get_room_by_slug(session, slug: str) -> Room | None:
    """Return an active room by slug, or None if not found."""
    result = await session.execute(
        select(Room).where(Room.slug == slug, Room.is_active == True)  # noqa: E712
    )
    return result.scalar_one_or_none()


def _ensure_timezone_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@router.post("/api/courses/{course_id}/rooms", response_model=RoomResponse)
async def create_room(
    course_id: str,
    body: RoomCreate,
    current_user: User = Depends(get_current_active_user),
):
    await _require_course_owner(course_id, current_user)

    expires_at = _parse_expires_at(body.expires_at)
    if expires_at and expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="过期时间必须晚于当前时间")

    # Generate a unique slug inside a single session. Retries handle the
    # extremely unlikely collision and concurrent insertion races.
    async with AsyncSessionLocal() as session:
        slug = _generate_slug()
        for attempt in range(MAX_SLUG_RETRIES):
            room = Room(
                id=str(uuid4()),
                slug=slug,
                course_id=course_id,
                created_by=current_user.id,
                title=body.title,
                password_hash=get_password_hash(body.password) if body.password else None,
                expires_at=expires_at,
                allow_anonymous=body.allow_anonymous,
                welcome_message=body.welcome_message,
                max_participants=body.max_participants,
                config_json=body.config_json,
                is_active=True,
            )
            session.add(room)
            try:
                await session.commit()
                await session.refresh(room)
                return _serialize_room(room)
            except IntegrityError:
                await session.rollback()
                if attempt == MAX_SLUG_RETRIES - 1:
                    raise HTTPException(
                        status_code=500, detail="无法生成唯一房间号"
                    ) from None
                slug = _generate_slug()

    # Unreachable, but keeps type checkers happy.
    raise HTTPException(status_code=500, detail="房间创建失败")


@router.get("/api/courses/{course_id}/rooms")
async def list_course_rooms(
    course_id: str,
    current_user: User = Depends(get_current_active_user),
):
    await _require_course_owner(course_id, current_user)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Room).where(Room.course_id == course_id).order_by(Room.created_at.desc())
        )
        rooms = result.scalars().all()

    return [_serialize_room(r) for r in rooms]


@router.get("/api/rooms/{slug}", response_model=RoomPublicResponse)
@limiter.limit("30/minute")
async def get_room(slug: str, request: Request):
    async with AsyncSessionLocal() as session:
        room = await _get_room_by_slug(session, slug)
        if room is None:
            raise HTTPException(status_code=404, detail="房间不存在或已关闭")
        if room.expires_at and room.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="房间已过期")
        response = _serialize_public_room(room)
    # Issue a signed session token so the client can join without being able
    # to forge arbitrary session_ids to inflate the participant count.
    raw_session = uuid4().hex
    response.session_token = _sign_session_id(room.id, raw_session)
    return response


@router.post("/api/rooms/{slug}/join")
@limiter.limit("10/minute")
async def join_room(slug: str, body: RoomJoinRequest, request: Request):
    async with AsyncSessionLocal() as session:
        room = await _get_room_by_slug(session, slug)
        if room is None:
            raise HTTPException(status_code=404, detail="房间不存在或已关闭")
        if room.expires_at and room.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="房间已过期")

        if room.password_hash:
            if not body.password:
                raise HTTPException(status_code=403, detail="该房间需要密码")
            if not verify_password(body.password, room.password_hash):
                raise HTTPException(status_code=403, detail="房间密码错误")

        should_count = True
        if body.session_id:
            # Reject client-fabricated session_ids: only tokens signed by this
            # server (issued via get_room) count for dedup, preventing an
            # attacker from rotating session_ids to bypass the participant cap.
            if not _verify_session_id(room.id, body.session_id):
                raise HTTPException(status_code=400, detail="会话凭据无效")
            existing_result = await session.execute(
                select(RoomEntrySession).where(
                    RoomEntrySession.room_id == room.id,
                    RoomEntrySession.session_id == body.session_id,
                )
            )
            if existing_result.scalar_one_or_none() is None:
                session.add(
                    RoomEntrySession(
                        id=str(uuid4()),
                        room_id=room.id,
                        session_id=body.session_id,
                    )
                )
            else:
                should_count = False

        if should_count:
            if room.max_participants is not None:
                # Atomic check-and-increment: use a conditional UPDATE that
                # only increments if the current count is below the limit.
                # This avoids the race between a separate SELECT and UPDATE.
                result = await session.execute(
                    Room.__table__.update()
                    .where(
                        Room.id == room.id,
                        Room.entry_count < room.max_participants,
                    )
                    .values(entry_count=Room.entry_count + 1)
                    .returning(Room.entry_count)
                )
                row = result.first()
                if row is None:
                    # No row updated means the condition (entry_count < max)
                    # was false, i.e. the room is full.
                    raise HTTPException(
                        status_code=429, detail="房间参与人数已达上限"
                    )
            else:
                # No participant limit; increment unconditionally.
                await session.execute(
                    Room.__table__.update()
                    .where(Room.id == room.id)
                    .values(entry_count=Room.entry_count + 1)
                )
        room.last_activity_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(room)

        return _serialize_public_room(room)


@router.patch("/api/rooms/{room_id}", response_model=RoomResponse)
async def update_room(
    room_id: str,
    body: RoomUpdate,
    current_user: User = Depends(get_current_active_user),
):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Room).where(Room.id == room_id))
        room = result.scalar_one_or_none()
        if room is None:
            raise HTTPException(status_code=404, detail="房间不存在")
        if room.created_by != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="没有权限操作该房间")

        if body.title is not None:
            room.title = body.title
        if body.is_active is not None:
            room.is_active = body.is_active
        if body.expires_at is not None:
            if body.expires_at == "":
                room.expires_at = None
            else:
                expires_at = _parse_expires_at(body.expires_at)
                if expires_at and expires_at <= datetime.now(timezone.utc):
                    raise HTTPException(status_code=400, detail="过期时间必须晚于当前时间")
                room.expires_at = expires_at
        if body.password is not None:
            room.password_hash = (
                get_password_hash(body.password) if body.password else None
            )
        if body.allow_anonymous is not None:
            room.allow_anonymous = body.allow_anonymous
        if body.welcome_message is not None:
            room.welcome_message = body.welcome_message
        if body.max_participants is not None:
            room.max_participants = body.max_participants
        if body.config_json is not None:
            room.config_json = body.config_json

        await session.commit()
        await session.refresh(room)

    return _serialize_room(room)


@router.delete("/api/rooms/{room_id}")
async def delete_room(
    room_id: str,
    current_user: User = Depends(get_current_active_user),
):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Room).where(Room.id == room_id))
        room = result.scalar_one_or_none()
        if room is None:
            raise HTTPException(status_code=404, detail="房间不存在")
        if room.created_by != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="没有权限操作该房间")

        await session.delete(room)
        await session.commit()

    return {"ok": True}
