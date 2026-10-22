"""Build MCP toolsets from approved servers in the database."""

import logging
from collections.abc import Sequence

from dash.agent.mcp import ServerTools
from dash.db import MCPServer, Store

log = logging.getLogger(__name__)


async def load_approved_mcp_toolsets(store: Store) -> Sequence[ServerTools]:
    """Load ServerTools for all approved MCP servers."""
    approved_servers = await store.mcp_servers(approved_only=True)
    toolsets: list[ServerTools] = []
    
    for server in approved_servers:
        # Try to build ServerTools for this server
        # We construct a McpServer object from the DB record
        from dash.agent.mcp import McpServer
        
        # Note: We don't have the exclude list from DB yet, but could add it
        mcp_server = McpServer(name=server.name, url=server.url, exclude=[])
        
        try:
            server_tools = ServerTools.connect(mcp_server)
            toolsets.append(server_tools)
        except Exception as e:
            log.error(f"Failed to load MCP tools for {server.name}: {e}")
    
    return toolsets
