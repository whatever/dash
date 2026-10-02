"""Stand-in for hermes-router: an OpenAI-style streaming endpoint that echoes.

Lets the UI, queue and worker run with no hermes and no API key. Set
HERMES_BASE_URL in .env to talk to a real hermes instead.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def chat(request: Request) -> StreamingResponse:
    body: dict[str, Any] = await request.json()
    messages: list[dict[str, str]] = body["messages"]
    system = next((m["content"] for m in messages if m["role"] == "system"), None)
    text = f"(fake hermes) You said: {messages[-1]['content']}"
    if system:
        text += f"\n\nMemories I was given:\n{system}"

    async def stream() -> AsyncIterator[str]:
        for word in text.split(" "):
            chunk = {"choices": [{"delta": {"content": word + " "}}]}
            yield f"data: {json.dumps(chunk)}\n\n"
            await asyncio.sleep(0.03)
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
