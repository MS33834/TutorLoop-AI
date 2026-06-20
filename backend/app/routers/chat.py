"""Chat and health endpoints."""

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.gateway import pool, stream_chat
from app.schemas import ChatRequest, HealthResponse, KeyHealthSummary

router = APIRouter()


async def _sse_event_stream(request: ChatRequest):
    messages = [m.model_dump() for m in request.messages]
    async for chunk in stream_chat(messages, model_type="text"):
        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/api/chat")
async def chat(request: ChatRequest):
    return StreamingResponse(
        _sse_event_stream(request),
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
