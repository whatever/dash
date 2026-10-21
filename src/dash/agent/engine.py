"""Runs one turn of the agent and streams it as deltas."""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from pydantic_ai import (
    Agent,
    AgentRunResultEvent,
    AgentStreamEvent,
    CancellationToken,
    Conversation,
    DeferredToolRequests,
    DeferredToolResults,
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
    ToolCallPart,
    ToolReturnPart,
    UsageLimits,
)
from pydantic_ai.capabilities import AgentCapability, WebSearch
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.litellm import LiteLLMProvider
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.usage import RunUsage

from dash.agent.deps import TurnDeps
from dash.agent.events import Delta, tool_label
from dash.agent.mcp import ServerTools
from dash.agent.policy import ToolPolicy
from dash.config import Thinking

INSTRUCTIONS = (
    "You are dash, a personal assistant that works for one person. "
    "Answer in Markdown, concisely and concretely. "
    "Use your tools when they help, and say what you did with them. "
    "When something fails, say so plainly instead of guessing."
)

OnDelta = Callable[[Delta], Awaitable[None]]
TOOL_STATUS = {
    "success": "completed",
    "failed": "failed",
    "denied": "denied",
    "interrupted": "interrupted",
}
Output = str | DeferredToolRequests


@dataclass(frozen=True)
class WaitingCall:
    """A tool call the turn stopped at until a person approves or denies it."""

    tool_call_id: str
    tool: str
    args: dict[str, Any]
    label: str


@dataclass(frozen=True)
class Turn:
    """How a turn ended: the conversation to store, whether it was stopped, and what waits."""

    conversation: Conversation
    stopped: bool = False
    waiting: list[WaitingCall] = field(default_factory=list[WaitingCall])


def build_model(name: str, base_url: str = "", api_key: str = "") -> Model | str:
    """Return the model for the given name, through an OpenAI-compatible API when a URL is set."""
    if not base_url:
        return name
    provider = LiteLLMProvider(api_base=base_url, api_key=api_key or None)
    return OpenAIChatModel(name, provider=provider)


def build_agent(
    model: Model | str,
    *,
    toolsets: Sequence[AbstractToolset[TurnDeps]] = (),
    policy: ToolPolicy | None = None,
    web_search: bool = False,
    thinking: Thinking | None = None,
) -> Agent[TurnDeps, Output]:
    """Return the agent for the given model, tools and thinking level.

    The policy hides `never` tools and makes `ask` tools wait for approval. Web search uses
    the model's own search where it has one, and DuckDuckGo otherwise.
    """
    policy = policy or ToolPolicy()
    settings = ModelSettings(thinking=thinking) if thinking else None
    capabilities: list[AgentCapability[TurnDeps]] = (
        [WebSearch(local="duckduckgo")] if web_search else []
    )
    return Agent(
        model,
        deps_type=TurnDeps,
        output_type=[str, DeferredToolRequests],
        instructions=INSTRUCTIONS,
        toolsets=[policy.offered(t) for t in toolsets],
        capabilities=capabilities,
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
    """Runs agent turns with a per-turn budget and the MCP servers that answer."""

    def __init__(
        self,
        agent: Agent[TurnDeps, Output],
        limits: UsageLimits,
        *,
        servers: Sequence[ServerTools] = (),
        policy: ToolPolicy | None = None,
    ) -> None:
        self.agent = agent
        self.limits = limits
        self.servers = list(servers)
        self.policy = policy or ToolPolicy()

    async def available(self, on_delta: OnDelta) -> list[AbstractToolset[TurnDeps]]:
        """Return the toolsets of the servers that answer, reporting the ones that don't."""
        toolsets: list[AbstractToolset[TurnDeps]] = []
        for server in self.servers:
            if await server.reachable():
                toolsets.append(self.policy.offered(server.toolset))
            else:
                message = f"The {server.name} tools are unavailable: the server did not answer."
                await on_delta(Delta("status", data={"message": message}))
        return toolsets

    async def run(
        self,
        conversation: Conversation,
        prompt: str | None,
        *,
        deps: TurnDeps,
        instructions: str | None,
        on_delta: OnDelta,
        cancel: CancellationToken,
        answers: DeferredToolResults | None = None,
    ) -> Turn:
        """Run one turn, stream it to `on_delta`, and return how it ended.

        `answers` carries a person's decisions on the calls the conversation waits on. A turn
        with no new prompt only continues those calls.
        """
        parts = StreamedParts()
        result: Conversation | None = None
        waiting: list[WaitingCall] = []
        toolsets = await self.available(on_delta)
        try:
            async with self.agent.run_stream_events(
                prompt,
                conversation=replace(conversation, usage=RunUsage()),
                deferred_tool_results=answers,
                deps=deps,
                instructions=instructions,
                usage_limits=self.limits,
                cancellation_token=cancel,
                toolsets=toolsets,
            ) as events:
                async for event in events:
                    if isinstance(event, AgentRunResultEvent):
                        result = event.result.conversation
                        if isinstance(event.result.output, DeferredToolRequests):
                            waiting = [_waiting(call) for call in event.result.output.approvals]
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
        return Turn(result, waiting=waiting)


def _waiting(call: ToolCallPart) -> WaitingCall:
    """Return the given tool call as one waiting for approval."""
    args = call.args_as_dict()
    label = tool_label(args) or call.tool_name
    return WaitingCall(call.tool_call_id, call.tool_name, args, label)


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
            status = TOOL_STATUS[done.outcome] if isinstance(done, ToolReturnPart) else "failed"
            data = {"tool": done.tool_name, "toolCallId": done.tool_call_id, "status": status}
            return [Delta("tool", data=data)]
        case _:
            return []
