"""Pydantic request/response schemas."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str = Field(..., examples=["user"])
    content: str = Field(..., examples=["如何解一元一次方程？"])


class ChatRequest(BaseModel):
    messages: list[Message]
    room_slug: Optional[str] = Field(None, examples=["room-abc123"])
    video_id: Optional[str] = Field(None, examples=["video-uuid"])
    screenshot: Optional[str] = Field(
        None, examples=["data:image/png;base64,..."]
    )
    timestamp: Optional[float] = Field(None, examples=[12.5])


class KeyHealthSummary(BaseModel):
    model: str
    status: str
    error_count: int
    avg_rtt_ms: float


class HealthResponse(BaseModel):
    status: str
    keys: list[KeyHealthSummary]


class InteractionCreate(BaseModel):
    user_id: str
    course_id: str
    video_id: Optional[str] = None
    video_timestamp: Optional[float] = None
    question_text: Optional[str] = None
    answer_text: Optional[str] = None
    is_correct: Optional[bool] = None
    help_count: int = 0
    watch_seconds: Optional[float] = None
    node_id: Optional[str] = None


class InteractionResponse(BaseModel):
    id: str
    user_id: Optional[str]
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
