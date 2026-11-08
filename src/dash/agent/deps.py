"""What every tool can see during a turn."""

import uuid
from dataclasses import dataclass, field

from dash.agent.workspace import DEFAULT_PROFILE


@dataclass(frozen=True)
class TurnDeps:
    """The conversation, job and workspace profile of a turn, and the tools saved rules allow."""

    conversation_id: uuid.UUID
    job_id: str
    approved: frozenset[str] = field(default_factory=frozenset[str])
    profile: str = DEFAULT_PROFILE
