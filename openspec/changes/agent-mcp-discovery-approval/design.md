# Design: MCP Tool Discovery and Approval

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────┐
│ Agent Tools                                             │
│ • install_mcp_tool(tool_name)                          │
│ • search_mcp_tools(query)                              │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│ Registry Discovery (registry.py)                        │
│ • Search GitHub modelcontextprotocol/servers repo      │
│ • Return matching tools with metadata                  │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│ Database Layer                                          │
│ • MCPServer (name, url, approved, timestamps)          │
│ • MCPToolApprovalRequest (mcp_server_id, status)       │
│ • Store methods for CRUD operations                    │
└─────────────────────────────────────────────────────────┘
```

### Database Schema

#### mcp_servers
- `id` - PK, auto-increment
- `name` - Tool name (e.g., "notion")
- `url` - GitHub repo URL
- `description` - What it does
- `approved` - Boolean, enabled?
- `approval_requested_at` - First request timestamp
- `approved_at` - Approval timestamp
- `created_at` - Record creation timestamp
- **Unique constraint**: (name, url)

#### mcp_tool_approval_requests
- `id` - PK, auto-increment
- `mcp_server_id` - FK to mcp_servers
- `source` - "agent" | "manual"
- `request_context` - JSON (user message, why requested, etc.)
- `status` - "pending" | "approved" | "rejected"
- `created_at` - Request timestamp
- `resolved_at` - Resolution timestamp (if resolved)

### Flow Diagram

```
User Chat: "Install notion"
        ↓
Agent: install_mcp_tool("notion")
        ↓
Registry: Search for "notion"
        ↓
Found: github.com/.../notion
        ↓
DB: Create MCPServer record (approved=false)
        ↓
DB: Create MCPToolApprovalRequest (status=pending)
        ↓
Inbox: Display approval item to user
        ↓
User: Click Approve
        ↓
DB: MCPServer.approved = true, approved_at = now()
        ↓
Agent next turn: load_approved_mcp_toolsets()
        ↓
Agent: Can now use notion tools
```

## Key Design Decisions

1. **Public Registry Only** - Start with official modelcontextprotocol servers
2. **Server-Level Control** - Approve whole server, not individual tools (simpler)
3. **Inbox Integration** - Reuse existing approval system
4. **Persistent Storage** - Approved servers survive restarts
5. **Async Discovery** - Non-blocking HTTP calls to GitHub
6. **Graceful Degradation** - Missing tools don't break agent
