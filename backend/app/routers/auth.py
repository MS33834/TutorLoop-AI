"""Authentication endpoints."""

import logging
from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

from app.config import settings
from app.db.postgres import AsyncSessionLocal
from app.limiter import limiter
from app.models.db import User
from app.schemas import (
    RefreshTokenRequest,
    RefreshTokenResponse,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
)
from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_current_active_user,
    get_password_hash,
    verify_password,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

# Refresh token cookie name. The cookie is HttpOnly + SameSite=Strict so it is
# never readable by JavaScript, mitigating refresh-token theft via XSS.
REFRESH_COOKIE_NAME = "tutorloop_refresh"
REFRESH_COOKIE_MAX_AGE = 30 * 24 * 3600  # 30 days, matches REFRESH_TOKEN_EXPIRE_DAYS


def _set_refresh_cookie(response: Response, refresh_token: str, request: Request) -> None:
    """Attach the refresh token as a hardened HttpOnly cookie.

    secure is driven by the request scheme so local dev over HTTP still works
    while production HTTPS gets the Secure flag. When ``settings.cookie_secure``
    is explicitly True, the Secure flag is forced on regardless of scheme
    (useful when TLS is terminated upstream and the app only sees HTTP).
    """
    is_https = (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto") == "https"
    )
    secure = bool(settings.cookie_secure) or is_https
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=REFRESH_COOKIE_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=secure,
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/auth")


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        created_at=user.created_at.isoformat(),
    )


def _issue_token_pair(user: User) -> TokenResponse:
    """Issue both an access token and a refresh token for a user."""
    expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token({"sub": user.id}, expires_delta=expires)
    refresh_token = create_refresh_token({"sub": user.id})
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=_user_response(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, body: UserRegister, response: Response):
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

    token_pair = _issue_token_pair(user)
    # Store the refresh token in an HttpOnly cookie so it is not exposed to JS
    # (mitigating XSS token theft). The access token stays in the response body
    # for the client to hold in memory only.
    _set_refresh_cookie(response, token_pair.refresh_token, request)
    return token_pair


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, body: UserLogin, response: Response):
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

    token_pair = _issue_token_pair(user)
    _set_refresh_cookie(response, token_pair.refresh_token, request)
    return token_pair


@router.post("/refresh", response_model=RefreshTokenResponse)
@limiter.limit("20/minute")
async def refresh_token(
    request: Request,
    response: Response,
    body: RefreshTokenRequest | None = None,
    refresh_cookie: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
):
    """Exchange a valid refresh token for a new access + refresh token pair.

    The refresh token is read from the HttpOnly cookie first (preferred, secure
    path) and falls back to the request body for backward compatibility with
    older clients that still send it as JSON.
    """
    raw_token = refresh_cookie or (body.refresh_token if body else None)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少刷新凭据",
        )

    payload = decode_refresh_token(raw_token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="刷新凭据无效",
        )

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被禁用",
        )

    expires = timedelta(minutes=settings.access_token_expire_minutes)
    new_access = create_access_token({"sub": user.id}, expires_delta=expires)
    new_refresh = create_refresh_token({"sub": user.id})
    # Rotate the refresh cookie with the new token.
    _set_refresh_cookie(response, new_refresh, request)
    return RefreshTokenResponse(access_token=new_access, refresh_token=new_refresh)


@router.post("/logout")
async def logout(response: Response):
    """Clear the refresh-token cookie to end the session server-side."""
    _clear_refresh_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_active_user)):
    return _user_response(user)
