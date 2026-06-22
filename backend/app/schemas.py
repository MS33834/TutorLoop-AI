"""Pydantic request/response schemas."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str = Field(..., examples=["user"])
    content: str = Field(..., max_length=4000, examples=["如何解一元一次方程？"])


class ChatRequest(BaseModel):
    messages: list[Message] = Field(..., min_length=1, max_length=50)
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
    user_id: str = Field(..., min_length=1, max_length=64)
    course_id: str = Field(..., min_length=1, max_length=64)
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
