"""Tools for discovering and requesting MCP servers."""

from pydantic import BaseModel
from pydantic_ai.toolsets import FunctionToolset

from dash.agent.registry import discover_mcp_tool
from dash.db import Store


class MCPToolInstallRequest(BaseModel):
    """Response from a tool install request."""

    tool_name: str
    status: str  # "requesting", "already_approved", "not_found"
    message: str


def mcp_discovery_tools(store: Store) -> FunctionToolset[None]:
    """Return tools for discovering and managing MCP tool installations."""
    tools = FunctionToolset[None]()

    @tools.tool_plain
    async def install_mcp_tool(tool_name: str, tool_description: str = "") -> MCPToolInstallRequest:
        """Request to install a new MCP tool.
        
        This searches the public MCP registry for the tool and sends an approval
        request to the user. Once approved, the tool will be available to the agent.
        
        Args:
            tool_name: Name of the MCP tool to install (e.g., "notion", "github", "linear")
            tool_description: Optional description of why you want this tool
        """
        # Search for the tool in the registry
        results = await discover_mcp_tool(tool_name)
        
        if not results:
            return MCPToolInstallRequest(
                tool_name=tool_name,
                status="not_found",
                message=f"Could not find '{tool_name}' in the MCP registry. Try searching for related tools.",
            )
        
        # Use the first result (best match)
        result = results[0]
        
        # Check if already installed
        existing = await store.find_mcp_server(result.name, result.url)
        if existing:
            if existing.approved:
                return MCPToolInstallRequest(
                    tool_name=result.name,
                    status="already_approved",
                    message=f"The {result.name} tools are already installed and approved.",
                )
            else:
                return MCPToolInstallRequest(
                    tool_name=result.name,
                    status="pending",
                    message=f"An approval request for {result.name} is already pending.",
                )
        
        # Create the server record and request approval
        server = await store.create_or_get_mcp_server(
            name=result.name,
            url=result.url,
            description=result.description,
        )
        
        context = {
            "tool_description": tool_description,
            "registry_url": result.url,
            "agent_request": True,
        }
        await store.request_mcp_approval(server.id, source="agent", context=context)
        
        return MCPToolInstallRequest(
            tool_name=result.name,
            status="requesting",
            message=f"Requested permission to install {result.name}. "
                    f"Approval: {result.description}. "
                    f"Please review and approve in your inbox.",
        )

    @tools.tool_plain
    async def search_mcp_tools(query: str) -> list[str]:
        """Search the public MCP registry for available tools.
        
        Returns a list of tool names that match the search query.
        """
        results = await discover_mcp_tool(query)
        return [f"{r.name}: {r.description}" for r in results]

    return tools
