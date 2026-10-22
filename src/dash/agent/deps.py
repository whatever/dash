"""What every tool can see during a turn."""

import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TurnDeps:
    """The conversation and job a turn runs for, and the tools saved rules let run unasked."""

    conversation_id: uuid.UUID
    job_id: str
    approved: frozenset[str] = field(default_factory=frozenset[str])
