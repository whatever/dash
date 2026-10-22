"""MCP servers that add tools to the agent, from `AGENT_MCP_SERVERS`."""

import asyncio
import logging
from dataclasses import dataclass

from pydantic import BaseModel, TypeAdapter
from pydantic_ai import RunContext, ToolDefinition
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.toolsets import AbstractToolset

from dash.agent.deps import TurnDeps

log = logging.getLogger(__name__)

PROBE_SECONDS = 5


class McpServer(BaseModel):
    """One configured MCP server: its name, its streamable-HTTP URL and the tools to leave out."""

    name: str
    url: str
    exclude: list[str] = []


_SERVERS = TypeAdapter(list[McpServer])


def parse(text: str) -> list[McpServer]:
    """Return the servers written as the given JSON list, or none."""
    return _SERVERS.validate_json(text) if text.strip() else []


@dataclass(frozen=True)
class ServerTools:
    """A server's tools, named `<server>_<tool>`, with the excluded ones left out."""

    name: str
    toolset: AbstractToolset[TurnDeps]

    @classmethod
    def build(
        cls, name: str, tools: AbstractToolset[TurnDeps], exclude: list[str]
    ) -> "ServerTools":
        """Return the given server tools, prefixed with its name and without the excluded ones."""
        excluded = set(exclude)

        def kept(ctx: RunContext[TurnDeps], tool: ToolDefinition) -> bool:
            return tool.name not in excluded

        return cls(name, tools.filtered(kept).prefixed(name))

    @classmethod
    def connect(cls, server: McpServer) -> "ServerTools":
        """Return the tools of the given server, reached over streamable HTTP."""
        return cls.build(server.name, MCPToolset(server.url), server.exclude)

    async def reachable(self) -> bool:
        """Return True if the server answers within a few seconds."""
        try:
            async with asyncio.timeout(PROBE_SECONDS), self.toolset:
                return True
        except Exception:
            log.warning("MCP server %s is unreachable", self.name, exc_info=True)
            return False
