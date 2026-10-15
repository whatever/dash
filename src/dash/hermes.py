"""OpenAI-compatible streaming client for the hermes router."""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

Kind = Literal["text", "reasoning", "tool", "status"]

CUSTOM_EVENTS: dict[str, Kind] = {"hermes.tool.progress": "tool", "hermes.status": "status"}


@dataclass(frozen=True)
class Delta:
    """One piece of a streamed hermes turn: answer text, reasoning text, or a tool/status update."""

    kind: Kind
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)


def conversation_key(conversation_id: object) -> str:
    """The stable hermes `conversation` name for a dash conversation.

    Derived only from the dash conversation id, so every turn of one conversation chains
    onto the same hermes history (across worker restarts and replicas)."""
    return f"dash:{conversation_id}"


def _tool_label(arguments: str, limit: int = 120) -> str:
    """A one-line preview of a function_call's JSON arguments."""
    try:
        args = json.loads(arguments) if arguments else {}
    except ValueError:
        args = arguments
    if isinstance(args, dict) and len(args) == 1:  # e.g. {"command": "ls"} -> "ls"
        args = next(iter(args.values()))
    text = args if isinstance(args, str) else json.dumps(args)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


class HermesError(RuntimeError):
    """A hermes turn that ended in `response.failed`."""


def parse_sse_frame(event: str | None, payload: str) -> list[Delta]:
    """Return the deltas carried by one /v1/responses SSE frame."""
    payload = payload.strip()
    if not payload or payload == "[DONE]":
        return []
    chunk: dict[str, Any] = json.loads(payload)
    event = event or chunk.get("type")
    if event in CUSTOM_EVENTS:
        return [Delta(CUSTOM_EVENTS[event], data=chunk)]
    if event == "response.output_text.delta":
        delta = chunk.get("delta")
        return [Delta("text", delta)] if isinstance(delta, str) and delta else []
    if event == "response.reasoning_summary_text.delta":
        delta = chunk.get("delta")
        return [Delta("reasoning", delta)] if isinstance(delta, str) and delta else []
    if event in ("response.output_item.added", "response.output_item.done"):
        item: dict[str, Any] = chunk.get("item") or {}
        if item.get("type") == "function_call" and event == "response.output_item.added":
            name = item.get("name", "")
            label = _tool_label(item.get("arguments", ""))
            return [
                Delta(
                    "tool",
                    data={
                        "tool": name,
                        "label": label or name,
                        "toolCallId": item.get("call_id"),
                        "status": "running",
                    },
                )
            ]
        if item.get("type") == "function_call" and event == "response.output_item.done":
            return [
                Delta(
                    "tool",
                    data={
                        "tool": item.get("name", ""),
                        "toolCallId": item.get("call_id"),
                        "status": "completed",
                    },
                )
            ]
        return []
    if event == "response.failed":
        response: dict[str, Any] = chunk.get("response") or {}
        error = response.get("error") or {}
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise HermesError(message or "response failed")
    return []


class Hermes:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.model = model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(
            base_url=base_url, headers=headers, timeout=httpx.Timeout(900, connect=10)
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def stream(
        self, conversation: str, text: str, instructions: str | None = None
    ) -> AsyncIterator[Delta]:
        """Yield each text, reasoning, tool and status delta of one hermes turn.

        Only the new user message is sent: hermes holds the earlier turns (tool calls and
        results included) under the `conversation` name and chains this turn onto them."""
        body: dict[str, Any] = {
            "model": self.model,
            "conversation": conversation,
            "input": text,
            "stream": True,
        }
        if instructions:
            body["instructions"] = instructions
        async with self._client.stream("POST", "/responses", json=body) as response:
            response.raise_for_status()
            event: str | None = None
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event = line.removeprefix("event:").strip()
                elif line.startswith("data:"):
                    for delta in parse_sse_frame(event, line.removeprefix("data:")):
                        yield delta
                elif not line:
                    event = None
