"""The agent that answers chat jobs, run inside the worker on Pydantic AI.

`engine` runs a turn and streams it as `events.Delta` values. `history` stores a conversation's
turns between jobs.
"""

from dash.agent.engine import Engine, Turn, build_agent, build_model
from dash.agent.events import Delta, tool_label

__all__ = [
    "Delta",
    "Engine",
    "Turn",
    "build_agent",
    "build_model",
    "tool_label",
]
