"""A conversation's turn history, as stored between turns."""

from collections.abc import Sequence
from typing import Any

from pydantic_ai import Conversation, ConversationTypeAdapter
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart


def dump(conversation: Conversation) -> dict[str, Any]:
    """Return the given conversation as JSON-ready data."""
    return ConversationTypeAdapter.dump_python(conversation, mode="json")


def load(data: dict[str, Any]) -> Conversation:
    """Return the conversation stored as the given data."""
    return ConversationTypeAdapter.validate_python(data)


def seed(turns: Sequence[tuple[str, str]]) -> Conversation:
    """Return a conversation that starts from the given `(role, content)` messages as text."""
    messages: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content)])
        if role == "user"
        else ModelResponse(parts=[TextPart(content)])
        for role, content in turns
        if content
    ]
    return Conversation(messages=messages)
