"""Pydantic request/response schemas."""

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserRegister(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    email: Optional[EmailStr] = Field(None, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def _normalize_username(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("password")
    @classmethod
    def _strong_password(cls, value: str) -> str:
        if not re.search(r"[a-z]", value):
            raise ValueError("密码必须包含小写字母")
        if not re.search(r"[A-Z]", value):
            raise ValueError("密码必须包含大写字母")
        if not re.search(r"\d", value):
            raise ValueError("密码必须包含数字")
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]", value):
            raise ValueError("密码必须包含特殊字符")
        return value


class UserLogin(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def _normalize_username(cls, value: str) -> str:
        return value.strip().lower()


class UserResponse(BaseModel):
    id: str
    username: str
    email: Optional[str]
    role: str
    created_at: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class RefreshTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class Message(BaseModel):
    role: Literal["system", "user", "assistant"] = Field(..., examples=["user"])
    content: str = Field(..., max_length=4000, examples=["如何解一元一次方程？"])


class ChatRequest(BaseModel):
    messages: list[Message] = Field(..., min_length=1, max_length=50)
    room_slug: Optional[str] = Field(None, examples=["room-abc123"])
    video_id: Optional[str] = Field(None, examples=["video-uuid"])
    screenshot: Optional[str] = Field(
        None, examples=["data:image/png;base64,..."]
    )
    timestamp: Optional[float] = Field(None, examples=[12.5])
    need_answer: bool = Field(
        False,
        description="当学生多次被引导仍无法回答时，直接给出答案而非继续苏格拉底式提问。",
    )


class RoomCreate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    password: Optional[str] = Field(None, max_length=64)
    expires_at: Optional[str] = Field(None, examples=["2025-12-31T23:59:59+00:00"])
    allow_anonymous: bool = True
    welcome_message: Optional[str] = Field(None, max_length=1000)
    max_participants: Optional[int] = Field(None, ge=1)
    config_json: Optional[dict[str, Any]] = None


class RoomUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None
    expires_at: Optional[str] = Field(None, max_length=64)
    password: Optional[str] = Field(None, max_length=64)
    allow_anonymous: Optional[bool] = None
    welcome_message: Optional[str] = Field(None, max_length=1000)
    max_participants: Optional[int] = Field(None, ge=1)
    config_json: Optional[dict[str, Any]] = None


class RoomResponse(BaseModel):
    id: str
    slug: str
    course_id: str
    title: Optional[str]
    allow_anonymous: bool
    is_active: bool
    expires_at: Optional[str]
    entry_count: int
    last_activity_at: Optional[str]
    welcome_message: Optional[str]
    max_participants: Optional[int]
    config_json: Optional[dict[str, Any]]
    created_at: str


class RoomPublicResponse(BaseModel):
    id: str
    slug: str
    course_id: str
    title: Optional[str]
    require_password: bool
    allow_anonymous: bool
    is_active: bool
    expires_at: Optional[str]


class RoomJoinRequest(BaseModel):
    password: Optional[str] = Field(None, max_length=64)
    session_id: Optional[str] = Field(None, max_length=64)


class KnowledgeNodeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    threshold: float = Field(0.8, ge=0.0, le=1.0)


class KnowledgeNodeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    threshold: Optional[float] = Field(None, ge=0.0, le=1.0)


class KnowledgeNodeResponse(BaseModel):
    id: str
    course_id: str
    name: str
    description: Optional[str]
    threshold: float


class KnowledgeEdgeCreate(BaseModel):
    source_id: str = Field(..., min_length=1, max_length=36)
    target_id: str = Field(..., min_length=1, max_length=36)
    relation: Optional[str] = Field("prerequisite", max_length=64)


class KnowledgeEdgeResponse(BaseModel):
    id: str
    course_id: str
    source_id: str
    target_id: str
    relation: str


class KeyHealthSummary(BaseModel):
    model: str
    status: str
    error_count: int
    avg_rtt_ms: float


class HealthResponse(BaseModel):
    status: str
    keys: list[KeyHealthSummary]


class InteractionCreate(BaseModel):
    user_id: Optional[str] = Field(None, min_length=1, max_length=64)
    course_id: str = Field(..., min_length=1, max_length=64)
    room_id: Optional[str] = Field(None, max_length=64)
    video_id: Optional[str] = Field(None, max_length=64)
    video_timestamp: Optional[float] = Field(None, ge=0)
    question_text: Optional[str] = Field(None, max_length=4000)
    answer_text: Optional[str] = Field(None, max_length=4000)
    is_correct: Optional[bool] = None
    help_count: int = Field(0, ge=0)
    watch_seconds: Optional[float] = Field(None, ge=0)
    node_id: Optional[str] = Field(None, max_length=64)


class InteractionResponse(BaseModel):
    id: str
    user_id: Optional[str]
    room_id: Optional[str]
    course_id: Optional[str]
    video_id: Optional[str]
    video_timestamp: Optional[float]
    question_text: Optional[str]
    answer_text: Optional[str]
    is_correct: Optional[bool]
    help_count: int
    watch_seconds: Optional[float]
    node_id: Optional[str]
    created_at: str
    mastery_updated: bool = False


class MasteryItem(BaseModel):
    node_id: str
    name: str
    description: Optional[str]
    threshold: float
    p_known: float
    interactions_count: int


class RecommendationResponse(BaseModel):
    recommendation: Optional[dict[str, Any]]
    message: Optional[str] = None


class ReportSummary(BaseModel):
    total_nodes: int
    mastered_nodes: int
    mastery_rate: float
    average_mastery: float
    interaction_count: int
    recent_7d_interactions: int
    total_watch_minutes: float
    total_help_count: int
    correct_count: int
    incorrect_count: int
    accuracy: float


class ReportResponse(BaseModel):
    user_id: str
    course_id: str
    course_title: str
    generated_at: str
    summary: ReportSummary
    mastery_items: list[MasteryItem]
    weak_nodes: list[dict[str, Any]]
