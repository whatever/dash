"""Runs one turn of the agent and streams it as deltas."""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field, replace

from pydantic_ai import (
    Agent,
    AgentRunResultEvent,
    AgentStreamEvent,
    CancellationToken,
    Conversation,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelSettings,
    PartDeltaEvent,
    PartStartEvent,
    RunCancelled,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    UsageLimits,
)
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.litellm import LiteLLMProvider
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.usage import RunUsage

from dash.agent.events import Delta, tool_label
from dash.config import Thinking

INSTRUCTIONS = (
    "You are dash, a personal assistant that works for one person. "
    "Answer in Markdown, concisely and concretely. "
    "Use your tools when they help, and say what you did with them. "
    "When something fails, say so plainly instead of guessing."
)

OnDelta = Callable[[Delta], Awaitable[None]]


@dataclass(frozen=True)
class Turn:
    """How a turn ended: the conversation to store, and whether it was stopped."""

    conversation: Conversation
    stopped: bool = False


def build_model(name: str, base_url: str = "", api_key: str = "") -> Model | str:
    """Return the model for the given name, through an OpenAI-compatible API when a URL is set."""
    if not base_url:
        return name
    provider = LiteLLMProvider(api_base=base_url, api_key=api_key or None)
    return OpenAIChatModel(name, provider=provider)


def build_agent(
    model: Model | str,
    *,
    toolsets: Sequence[AbstractToolset[None]] = (),
    thinking: Thinking | None = None,
) -> Agent[None, str]:
    """Return the agent for the given model, tools and thinking level."""
    settings = ModelSettings(thinking=thinking) if thinking else None
    return Agent(
        model,
        deps_type=type(None),
        instructions=INSTRUCTIONS,
        toolsets=list(toolsets),
        model_settings=settings,
    )


@dataclass
class StreamedParts:
    """The text already emitted for each part of the model response being streamed."""

    seen: dict[int, str] = field(default_factory=dict[int, str])

    def start(self, index: int, content: str) -> str:
        """Record a started part and return the text not yet emitted for it."""
        before = self.seen.get(index, "")
        self.seen[index] = content
        return content[len(before) :] if content.startswith(before) else ""

    def add(self, index: int, delta: str) -> str:
        """Record a delta for a part and return it."""
        self.seen[index] = self.seen.get(index, "") + delta
        return delta


class Engine:
    """Runs agent turns with a per-turn budget."""

    def __init__(self, agent: Agent[None, str], limits: UsageLimits) -> None:
        self.agent = agent
        self.limits = limits

    async def run(
        self,
        conversation: Conversation,
        prompt: str,
        *,
        instructions: str | None,
        on_delta: OnDelta,
        cancel: CancellationToken,
    ) -> Turn:
        """Run one turn, stream it to `on_delta`, and return how it ended."""
        parts = StreamedParts()
        result: Conversation | None = None
        try:
            async with self.agent.run_stream_events(
                prompt,
                conversation=replace(conversation, usage=RunUsage()),
                instructions=instructions,
                usage_limits=self.limits,
                cancellation_token=cancel,
            ) as events:
                async for event in events:
                    if isinstance(event, AgentRunResultEvent):
                        result = event.result.conversation
                        continue
                    for delta in _deltas(event, parts):
                        await on_delta(delta)
        except RunCancelled as ex:
            stopped = Conversation(
                messages=ex.all_messages(),
                usage=ex.usage,
                conversation_id=ex.conversation_id or conversation.conversation_id,
            )
            return Turn(stopped, stopped=True)
        if result is None:
            raise RuntimeError("The run ended without a result.")
        return Turn(result)


def _deltas(event: AgentStreamEvent, parts: StreamedParts) -> list[Delta]:
    """Return the deltas carried by one stream event."""
    match event:
        case PartStartEvent(index=index, part=TextPart(content=content)):
            text = parts.start(index, content)
            return [Delta("text", text)] if text else []
        case PartStartEvent(index=index, part=ThinkingPart(content=content)):
            text = parts.start(index, content)
            return [Delta("reasoning", text)] if text else []
        case PartDeltaEvent(index=index, delta=TextPartDelta(content_delta=text)) if text:
            return [Delta("text", parts.add(index, text))]
        case PartDeltaEvent(index=index, delta=ThinkingPartDelta(content_delta=text)) if text:
            return [Delta("reasoning", parts.add(index, text))]
        case FunctionToolCallEvent(part=call):
            parts.seen.clear()
            label = tool_label(call.args) or call.tool_name
            data = {
                "tool": call.tool_name,
                "label": label,
                "toolCallId": call.tool_call_id,
                "status": "running",
            }
            return [Delta("tool", data=data)]
        case FunctionToolResultEvent(part=done):
            parts.seen.clear()
            data = {"tool": done.tool_name, "toolCallId": done.tool_call_id, "status": "completed"}
            return [Delta("tool", data=data)]
        case _:
            return []
