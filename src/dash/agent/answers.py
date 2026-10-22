"""A person's decisions on waiting tool calls, in the form the next run takes."""

from collections.abc import Sequence

from pydantic_ai import DeferredToolRequests, DeferredToolResults, ToolApproved, ToolDenied

from dash.db import InboxItem
from dash.inbox import ALLOW, ALLOW_ALWAYS, EXPIRED, RESOLVED, SUPERSEDED

DENIED = "The person denied this call."
SUPERSEDED_MESSAGE = "The person sent a new message instead of answering, so this call did not run."
EXPIRED_MESSAGE = "No one answered within 24 hours, so this call did not run."
UNANSWERED = "No one answered, so this call did not run."


def answer(item: InboxItem | None) -> ToolApproved | ToolDenied:
    """Return the decision recorded on the given approval item."""
    if item is None:
        return ToolDenied(UNANSWERED)
    if item.status == EXPIRED:
        return ToolDenied(EXPIRED_MESSAGE)
    if item.status != RESOLVED or item.resolution is None:
        return ToolDenied(UNANSWERED)
    if item.resolution.get("decision") in (ALLOW, ALLOW_ALWAYS):
        return ToolApproved()
    if item.resolution.get("reason") == SUPERSEDED:
        return ToolDenied(SUPERSEDED_MESSAGE)
    return ToolDenied(DENIED)


def answers(pending: DeferredToolRequests, items: Sequence[InboxItem]) -> DeferredToolResults:
    """Return a decision for every call the conversation waits on, from its approval items."""
    by_call = {str(i.data.get("tool_call_id")): i for i in items}
    return DeferredToolResults(
        approvals={c.tool_call_id: answer(by_call.get(c.tool_call_id)) for c in pending.approvals}
    )
