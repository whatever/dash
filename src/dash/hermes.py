"""OpenAI-compatible streaming client for the hermes router."""

import json
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

import httpx


def parse_sse_line(line: str) -> str | None:
    """The text delta in one `data:` line. None for keep-alives, role-only chunks and `[DONE]`."""
    if not line.startswith("data:"):
        return None
    payload = line.removeprefix("data:").strip()
    if not payload or payload == "[DONE]":
        return None
    chunk: dict[str, Any] = json.loads(payload)
    choices: list[dict[str, Any]] = chunk.get("choices") or []
    if not choices:
        return None
    delta: dict[str, Any] = choices[0].get("delta") or {}
    return delta.get("content") or None


class Hermes:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.model = model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        # Agent turns can run tools for minutes; only the connect is short.
        self._client = httpx.AsyncClient(
            base_url=base_url, headers=headers, timeout=httpx.Timeout(900, connect=10)
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def stream(self, messages: Sequence[Mapping[str, str]]) -> AsyncIterator[str]:
        body = {"model": self.model, "messages": list(messages), "stream": True}
        async with self._client.stream("POST", "/chat/completions", json=body) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                delta = parse_sse_line(line)
                if delta:
                    yield delta
