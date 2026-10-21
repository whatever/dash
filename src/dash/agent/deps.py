"""What every tool can see during a turn."""

import json
import uuid
from dataclasses import dataclass, field
from typing import Any


def call_key(tool: str, args: dict[str, Any]) -> str:
    """Return a key that is the same for two calls only when the tool and arguments match."""
    return f"{tool}\0{json.dumps(args, sort_keys=True, separators=(',', ':'))}"


@dataclass(frozen=True)
class TurnDeps:
    """The conversation and job a turn runs for, and the calls saved rules let run unasked."""

    conversation_id: uuid.UUID
    job_id: str
    approved: frozenset[str] = field(default_factory=frozenset[str])
