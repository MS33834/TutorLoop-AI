"""Mock local LLM server for Phase 1 integration testing."""

import asyncio
import json

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI(title="Mock Local LLM")


async def _token_stream():
    tokens = ["你", "好", "！", "这", "是", "本", "地", "兜", "底", "模", "型", "。"]
    for token in tokens:
        chunk = {"choices": [{"delta": {"content": token}}]}
        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.05)
    yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    return StreamingResponse(
        _token_stream(),
        media_type="text/event-stream",
    )
