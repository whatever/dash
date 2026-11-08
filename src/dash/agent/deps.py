"""What every tool can see during a turn."""

import uuid
from dataclasses import dataclass, field

from dash.agent.workspace import DEFAULT_PROFILE


@dataclass(frozen=True)
class TurnDeps:
    """The conversation, job, workspace profile and tool limit of a turn, and approved tools."""

    conversation_id: uuid.UUID
    job_id: str
    approved: frozenset[str] = field(default_factory=frozenset[str])
    profile: str = DEFAULT_PROFILE
    tools: frozenset[str] | None = None
