"""Discover and search for MCP tools from the public registry."""

import logging
from dataclasses import dataclass

import httpx
from pydantic import BaseModel

log = logging.getLogger(__name__)

# The public MCP registry (this is where modelcontextprotocol publishes official tools)
REGISTRY_URL = "https://raw.githubusercontent.com/modelcontextprotocol/servers/main/README.md"
REGISTRY_GITHUB_API = "https://api.github.com/repos/modelcontextprotocol/servers"


@dataclass
class ToolSearchResult:
    """A discovered MCP tool from the registry."""

    name: str
    description: str
    url: str  # npm package URL or GitHub repo
    mcp_url: str | None = None  # URL to reach the MCP server if known


class RegistrySearch:
    """Search for and discover MCP tools from the public registry."""

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    async def search(self, query: str) -> list[ToolSearchResult]:
        """Search the MCP registry for tools matching the query.
        
        Returns tools from the official modelcontextprotocol/servers GitHub repo
        that match the search term.
        """
        try:
            # Fetch the GitHub API to get the list of servers
            response = await self.client.get(
                f"{REGISTRY_GITHUB_API}/contents",
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            response.raise_for_status()
            
            entries = response.json()
            results: list[ToolSearchResult] = []
            
            query_lower = query.lower()
            
            for entry in entries:
                if entry.get("type") == "dir":
                    # Each directory is a server, check if name matches
                    name = entry["name"]
                    if query_lower in name.lower():
                        # Try to get package.json for more info
                        package_url = f"{REGISTRY_GITHUB_API}/contents/{name}/package.json"
                        try:
                            pkg_response = await self.client.get(
                                package_url,
                                headers={"Accept": "application/vnd.github.v3.raw"},
                            )
                            if pkg_response.status_code == 200:
                                import json
                                pkg = json.loads(pkg_response.text)
                                description = pkg.get("description", f"MCP server: {name}")
                                
                                results.append(ToolSearchResult(
                                    name=name,
                                    description=description,
                                    url=f"https://github.com/modelcontextprotocol/servers/tree/main/{name}",
                                    mcp_url=None,  # Will be determined by user/config
                                ))
                        except Exception as e:
                            log.debug(f"Failed to fetch package.json for {name}: {e}")
                            # Still add it with basic info
                            results.append(ToolSearchResult(
                                name=name,
                                description=f"MCP server: {name}",
                                url=f"https://github.com/modelcontextprotocol/servers/tree/main/{name}",
                            ))
            
            return results
        except Exception as e:
            log.error(f"Failed to search MCP registry: {e}")
            return []


async def discover_mcp_tool(query: str) -> list[ToolSearchResult]:
    """Convenience function to search for MCP tools."""
    search = RegistrySearch()
    try:
        return await search.search(query)
    finally:
        await search.close()
