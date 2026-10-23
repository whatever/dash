# Spec: MCP Tool Discovery

## Overview

The discovery module searches the public MCP registry and returns matching tools with metadata.

## API

### RegistrySearch

```python
class RegistrySearch:
    async def search(query: str) -> list[ToolSearchResult]
    async def close() -> None
```

### ToolSearchResult

```python
@dataclass
class ToolSearchResult:
    name: str                    # e.g., "notion"
    description: str             # What it does
    url: str                      # GitHub repo URL
    mcp_url: str | None = None   # MCP server endpoint (if known)
```

### Convenience Function

```python
async def discover_mcp_tool(query: str) -> list[ToolSearchResult]:
    """Search and return matching tools."""
```

## Behavior

### search(query)

**Input**: `query` - Case-insensitive search string

**Process**:
1. Fetch https://api.github.com/repos/modelcontextprotocol/servers/contents
2. Filter directories where name contains query (case-insensitive)
3. For each match, fetch package.json for description
4. Return ToolSearchResult for each match, sorted by relevance

**Output**: List of ToolSearchResult, sorted by name match quality

**Error Handling**:
- Network errors: Log and return empty list
- Invalid JSON: Log and skip entry
- Missing package.json: Include with generic description

**Examples**:
```
search("notion") → [ToolSearchResult(name="notion", ...)]
search("git") → [ToolSearchResult(name="github", ...), ...]
search("xyz") → []
```

## Implementation Details

- Uses httpx.AsyncClient for requests
- GitHub API rate limit: 60 req/hour unauthenticated
- Timeout: 10 seconds default
- Caches nothing (fresh data on each search)

## Testing

- [ ] Search for existing tool ("notion", "github") returns results
- [ ] Search for non-existent tool returns empty list
- [ ] Network timeout handled gracefully
- [ ] Invalid JSON in package.json doesn't crash
- [ ] Case-insensitive search works
