"""Authentication endpoints."""

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.config import settings
from app.db.postgres import AsyncSessionLocal
from app.limiter import limiter
from app.models.db import User
from app.schemas import TokenResponse, UserLogin, UserRegister, UserResponse
from app.services.auth_service import (
    create_access_token,
    get_current_active_user,
    get_password_hash,
    verify_password,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        created_at=user.created_at.isoformat(),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, body: UserRegister):
    async with AsyncSessionLocal() as session:
        existing = await session.execute(
            select(User).where(User.username == body.username)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="用户名已存在",
            )

        if body.email:
            existing_email = await session.execute(
                select(User).where(User.email == body.email)
            )
            if existing_email.scalar_one_or_none() is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="邮箱已存在",
                )

        user = User(
            username=body.username,
            email=body.email,
            password_hash=get_password_hash(body.password),
            role="student",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token({"sub": user.id}, expires_delta=expires)
    return TokenResponse(access_token=access_token, user=_user_response(user))


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, body: UserLogin):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.username == body.username)
        )
        user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用",
        )

    expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token({"sub": user.id}, expires_delta=expires)
    return TokenResponse(access_token=access_token, user=_user_response(user))


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_active_user)):
    return _user_response(user)
