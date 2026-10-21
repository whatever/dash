"""The agent's own tools: sandbox commands, web pages, memories and inbox messages."""

from typing import Annotated

import httpx
from pydantic import BaseModel, Field
from pydantic_ai import RunContext
from pydantic_ai.toolsets import FunctionToolset

from dash.agent.deps import TurnDeps
from dash.agent.sandbox import CommandResult, Sandbox
from dash.agent.web import Fetcher, RefusedError
from dash.db import Store
from dash.inbox import MESSAGE
from dash.inbox.db import InboxStore
from dash.memory import DUPLICATE_DISTANCE, Embedder

MEMORY_RESULTS = 8


class MemoryHit(BaseModel):
    """A stored memory and how far it is from the query (0 is identical)."""

    content: str
    distance: float


def sandbox_tools(sandbox: Sandbox) -> FunctionToolset[TurnDeps]:
    """Return the `run_command` tool for the given sandbox."""
    tools = FunctionToolset[TurnDeps]()

    @tools.tool_plain
    async def run_command(command: str) -> CommandResult:
        """Run a shell command in your sandbox's workspace and return its exit code and output.

        The sandbox has git, gh, python3, ripgrep and fd. Commands stop after 90 seconds.
        """
        return await sandbox.run(command)

    return tools


def web_tools(fetcher: Fetcher) -> FunctionToolset[TurnDeps]:
    """Return the `fetch_url` tool."""
    tools = FunctionToolset[TurnDeps]()

    @tools.tool_plain
    async def fetch_url(url: str) -> str:
        """Fetch a public http or https page and return its status, final URL and text."""
        try:
            return await fetcher.fetch(url)
        except RefusedError as ex:
            return f"Refused: {ex}"
        except httpx.HTTPError as ex:
            return f"Failed: {ex}"

    return tools


def memory_tools(store: Store, embedder: Embedder) -> FunctionToolset[TurnDeps]:
    """Return the `search_memories` and `remember` tools."""
    tools = FunctionToolset[TurnDeps]()

    @tools.tool_plain
    async def search_memories(query: str) -> list[MemoryHit]:
        """Return the stored memories nearest the given query."""
        hits = await store.search_memories(await embedder.embed(query), MEMORY_RESULTS)
        return [MemoryHit(content=m.content, distance=round(d, 4)) for m, d in hits]

    @tools.tool_plain
    async def remember(fact: str) -> str:
        """Store a durable fact about the user, written as one short sentence."""
        embedding = await embedder.embed(fact)
        nearest = await store.search_memories(embedding, 1)
        if nearest and nearest[0][1] < DUPLICATE_DISTANCE:
            return f"Already known: {nearest[0][0].content}"
        await store.add_memory(fact, embedding, source="agent")
        return "Remembered."

    return tools


def inbox_tools(inbox: InboxStore) -> FunctionToolset[TurnDeps]:
    """Return the `leave_message` tool."""
    tools = FunctionToolset[TurnDeps]()

    @tools.tool
    async def leave_message(
        ctx: RunContext[TurnDeps],
        title: Annotated[str, Field(min_length=1, max_length=120)],
        body: Annotated[str, Field(max_length=4000)],
        sources: Annotated[list[str], Field(max_length=10)] | None = None,
    ) -> str:
        """Leave the person a note in their inbox, to read later. It needs no answer.

        Use it for something worth keeping that should outlive this chat, with the URLs it
        came from as sources.
        """
        item = await inbox.add(
            kind=MESSAGE,
            title=title,
            body=body,
            data={"sources": sources or []},
            conversation_id=ctx.deps.conversation_id,
            job_id=ctx.deps.job_id,
        )
        return f"Left message {item.id} in the inbox."

    return tools
