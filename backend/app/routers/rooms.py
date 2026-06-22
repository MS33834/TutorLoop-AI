"""Learning room endpoints for TutorLoop AI."""

import logging
import secrets
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db.postgres import AsyncSessionLocal
from app.models.db import Course, Room, User
from app.schemas import RoomCreate, RoomJoinRequest, RoomPublicResponse, RoomResponse
from app.services.auth_service import (
    get_current_active_user,
    get_password_hash,
    verify_password,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _generate_slug() -> str:
    """Generate a short URL-safe room slug."""
    return secrets.token_urlsafe(6)[:8]


def _serialize_room(room: Room) -> RoomResponse:
    return RoomResponse(
        id=room.id,
        slug=room.slug,
        course_id=room.course_id,
        title=room.title,
        allow_anonymous=room.allow_anonymous,
        is_active=room.is_active,
        expires_at=room.expires_at.isoformat() if room.expires_at else None,
        created_at=room.created_at.isoformat(),
    )


def _serialize_public_room(room: Room) -> RoomPublicResponse:
    return RoomPublicResponse(
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
            raise HTTPException(status_code=404, detail="Course not found")
        if course.created_by != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="没有权限操作该课程")
        return course


async def _get_room_by_slug(slug: str) -> Room:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Room).where(Room.slug == slug, Room.is_active == True)
        )
        room = result.scalar_one_or_none()
        if room is None:
            raise HTTPException(status_code=404, detail="房间不存在或已关闭")
        return room


@router.post("/api/courses/{course_id}/rooms", response_model=RoomResponse)
async def create_room(
    course_id: str,
    body: RoomCreate,
    current_user: User = Depends(get_current_active_user),
):
    await _require_course_owner(course_id, current_user)

    expires_at = None
    if body.expires_at:
        try:
            expires_at = datetime.fromisoformat(body.expires_at)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"expires_at 格式错误: {exc}"
            ) from exc

    slug = _generate_slug()
    # Ensure slug uniqueness; retry a few times if collision occurs.
    for _ in range(5):
        async with AsyncSessionLocal() as session:
            existing = await session.execute(select(Room).where(Room.slug == slug))
            if existing.scalar_one_or_none() is None:
                break
        slug = _generate_slug()
    else:
        raise HTTPException(status_code=500, detail="无法生成唯一房间号")

    room = Room(
        id=str(uuid4()),
        slug=slug,
        course_id=course_id,
        created_by=current_user.id,
        title=body.title,
        password_hash=get_password_hash(body.password) if body.password else None,
        expires_at=expires_at,
        allow_anonymous=body.allow_anonymous,
        is_active=True,
    )

    async with AsyncSessionLocal() as session:
        session.add(room)
        await session.commit()
        await session.refresh(room)

    return _serialize_room(room)


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
async def get_room(slug: str):
    room = await _get_room_by_slug(slug)
    if room.expires_at and room.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="房间已过期")
    return _serialize_public_room(room)


@router.post("/api/rooms/{slug}/join")
async def join_room(slug: str, body: RoomJoinRequest):
    room = await _get_room_by_slug(slug)
    if room.expires_at and room.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="房间已过期")

    if room.password_hash:
        if not body.password:
            raise HTTPException(status_code=403, detail="该房间需要密码")
        if not verify_password(body.password, room.password_hash):
            raise HTTPException(status_code=403, detail="房间密码错误")

    return _serialize_public_room(room)


class RoomUpdate(BaseModel):
    title: str | None = Field(None, max_length=255)
    is_active: bool | None = None
    expires_at: str | None = Field(None, max_length=64)
    password: str | None = Field(None, max_length=64)


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
                try:
                    expires_at = datetime.fromisoformat(body.expires_at)
                    if expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=timezone.utc)
                    room.expires_at = expires_at
                except ValueError as exc:
                    raise HTTPException(
                        status_code=400, detail=f"expires_at 格式错误: {exc}"
                    ) from exc
        if body.password is not None:
            room.password_hash = (
                get_password_hash(body.password) if body.password else None
            )

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
