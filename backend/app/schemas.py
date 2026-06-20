"""Pydantic request/response schemas."""

from typing import Optional

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
