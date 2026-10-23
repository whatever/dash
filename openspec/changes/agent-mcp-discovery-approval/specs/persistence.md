# Spec: Persistence Layer

## Overview

Database operations for MCP server and approval request management.

## Database Tables

### mcp_servers

```sql
CREATE TABLE mcp_servers (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    approved BOOLEAN NOT NULL DEFAULT FALSE,
    approval_requested_at TIMESTAMP WITH TIME ZONE,
    approved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (name, url)
);
```

### mcp_tool_approval_requests

```sql
CREATE TABLE mcp_tool_approval_requests (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    mcp_server_id BIGINT NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    request_context JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMP WITH TIME ZONE,
    INDEX mcp_server_id
);
```

## Store API

### Query Methods

```python
async def mcp_servers(approved_only: bool = False) -> Sequence[MCPServer]
# Returns all servers, or only approved ones

async def get_mcp_server(server_id: int) -> MCPServer | None
# Fetch by ID

async def find_mcp_server(name: str, url: str) -> MCPServer | None
# Find by name and URL (unique constraint)

async def pending_approval_requests() -> Sequence[MCPToolApprovalRequest]
# Get all pending requests for inbox display
```

### Create/Update Methods

```python
async def create_or_get_mcp_server(name: str, url: str, description: str = "") -> MCPServer
# Create if doesn't exist, return existing if it does

async def request_mcp_approval(
    server_id: int,
    source: str = "agent",
    context: dict[str, Any] | None = None,
) -> MCPToolApprovalRequest
# Create approval request, update server.approval_requested_at

async def approve_mcp_server(server_id: int) -> MCPServer | None
# Set approved=True, approved_at=now()
# Mark associated requests as approved

async def reject_mcp_server(server_id: int) -> MCPServer | None
# Delete server (CASCADE), mark requests as rejected
```

## Data Consistency

### Constraints

- `mcp_servers(name, url)` - Unique constraint prevents duplicates
- `mcp_tool_approval_requests.mcp_server_id` - FK with CASCADE delete
- Status values: "pending", "approved", "rejected"

### Invariants

- Approved server: approved=True, approved_at NOT NULL, approved_requested_at NOT NULL
- Pending request: status="pending", resolved_at IS NULL
- Resolved request: resolved_at NOT NULL

## Migration

Alembic migration `0007_mcp_servers.py`:
- Creates both tables with constraints
- Creates indexes
- Reversible (downgrade supported)

## Testing

- [ ] Tables created with correct schema
- [ ] Unique constraint prevents duplicate servers
- [ ] Foreign key cascade works
- [ ] Timestamps auto-populated
- [ ] All Store methods CRUD correctly
- [ ] Migration up/down works
