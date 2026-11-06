# Tasks: MCP Tool Discovery and Approval

## PR 1: Database Schema & Persistence Layer

**Goal**: Establish database tables and Store methods for MCP server management

### Tasks
- [ ] Add MCPServer model to src/dash/db.py
- [ ] Add MCPToolApprovalRequest model to src/dash/db.py
- [ ] Add Store methods:
  - [ ] mcp_servers(approved_only=False)
  - [ ] get_mcp_server(server_id)
  - [ ] find_mcp_server(name, url)
  - [ ] create_or_get_mcp_server(name, url, description)
  - [ ] request_mcp_approval(server_id, source, context)
  - [ ] pending_approval_requests()
  - [ ] approve_mcp_server(server_id)
  - [ ] reject_mcp_server(server_id)
- [ ] Create migration 0007_mcp_servers.py
- [ ] Test: Verify tables create and CRUD operations work

## PR 2: Registry Discovery Module

**Goal**: Implement MCP tool discovery from public registry

### Tasks
- [ ] Create src/dash/agent/registry.py
- [ ] Implement RegistrySearch class:
  - [ ] search(query) - Search GitHub repo
  - [ ] Parse package.json for descriptions
  - [ ] Return ToolSearchResult list
- [ ] Add discover_mcp_tool() convenience function
- [ ] Handle HTTP errors gracefully
- [ ] Test: Search for "notion", "github", etc. returns results

## PR 3: Agent Tools & Installation Workflow

**Goal**: Add tools agents can use to request MCP installations

### Tasks
- [ ] Create src/dash/agent/mcp_tools.py
- [ ] Implement mcp_discovery_tools() toolset factory:
  - [ ] install_mcp_tool(tool_name, description) tool
  - [ ] search_mcp_tools(query) tool
- [ ] install_mcp_tool logic:
  - [ ] Search registry for tool
  - [ ] Check if already installed
  - [ ] Create MCPServer + approval request
  - [ ] Return appropriate status message
- [ ] Test: Requesting notion tool creates DB records correctly

## PR 4: Engine Integration & Loading

**Goal**: Wire approved MCP tools into the agent engine

### Tasks
- [ ] Create src/dash/agent/mcp_config.py
- [ ] Implement load_approved_mcp_toolsets()
  - [ ] Query approved servers from DB
  - [ ] Build ServerTools for each
  - [ ] Handle connection errors gracefully
- [ ] Update engine initialization to:
  - [ ] Call load_approved_mcp_toolsets()
  - [ ] Add mcp_discovery_tools() to agent
  - [ ] Compose all toolsets
- [ ] Test: Agent can call install_mcp_tool and search_mcp_tools

## Testing Strategy

For each PR:
- **Unit tests**: Database operations, registry search, tool execution
- **Integration tests**: End-to-end: agent → registry → database → approval
- **Manual tests**: Chat with agent, request installation, verify inbox

## Verification Checklist

- [ ] All database migrations apply cleanly
- [ ] Registry searches return expected results
- [ ] Agent can discover and request tools
- [ ] Approval requests appear in database
- [ ] Approved tools load on next agent turn
- [ ] Agent can use newly approved tools
- [ ] Graceful handling of network/registry failures
