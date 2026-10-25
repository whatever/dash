"""Decides what an inbound job is for before the worker acts on it."""

from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel, Field

from dash.queue import UPDATE, Job


class Action(StrEnum):
    """What the worker does with a job."""

    CHAT = "chat"
    FLAG = "flag"
    IGNORE = "ignore"
    REMEMBER = "remember"


class RoutedBy(StrEnum):
    """The stage that made a decision."""

    FALLBACK = "fallback"
    MODEL = "model"
    RULES = "rules"


class Decision(BaseModel):
    """What to do with a job, which stage decided, and why."""

    action: Action
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str = Field(max_length=200)
    routed_by: RoutedBy


Stage = Callable[[Job, Action | None], Decision | None]


def rules(job: Job, source_route: Action | None) -> Decision | None:
    """Return the fixed decision for a chat job or a source with a route."""
    if job.kind != UPDATE:
        return Decision(
            action=Action.CHAT, reason="Chat jobs always chat.", routed_by=RoutedBy.RULES
        )
    if source_route is not None:
        return Decision(
            action=source_route,
            reason=f"The source's route is {source_route}.",
            routed_by=RoutedBy.RULES,
        )
    return None


def fallback(job: Job, source_route: Action | None) -> Decision:
    """Return the decision that keeps today's behaviour: remember the update."""
    return Decision(action=Action.REMEMBER, reason="No rule applied.", routed_by=RoutedBy.FALLBACK)


STAGES: tuple[Stage, ...] = (rules,)


def route(job: Job, source_route: Action | None) -> Decision:
    """Return the first stage's decision for the job, or the fallback."""
    return next(
        (d for d in (stage(job, source_route) for stage in STAGES) if d is not None),
        fallback(job, source_route),
    )
