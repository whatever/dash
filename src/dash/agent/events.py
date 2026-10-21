"""The pieces of a streamed turn, as the worker turns them into job events."""

import json
from dataclasses import dataclass, field
from typing import Any, Literal

Kind = Literal["text", "reasoning", "tool", "status"]

LABEL_CHARS = 120


@dataclass(frozen=True)
class Delta:
    """One piece of a streamed turn: answer text, reasoning text, or a tool/status update."""

    kind: Kind
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict[str, Any])


def tool_label(arguments: str | dict[str, Any] | None, limit: int = LABEL_CHARS) -> str:
    """Return a one-line preview of a tool call's arguments."""
    args: Any = arguments
    if isinstance(arguments, str):
        try:
            args = json.loads(arguments) if arguments else {}
        except ValueError:
            args = arguments
    if isinstance(args, dict) and len(args) == 1:  # pyright: ignore[reportUnknownArgumentType]
        args = next(iter(args.values()))  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
    text = args if isinstance(args, str) else json.dumps(args or {})
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
