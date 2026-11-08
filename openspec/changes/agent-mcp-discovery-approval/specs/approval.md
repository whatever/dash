# Spec: MCP Tool Approval Workflow

## Overview

Approval flow: agent requests tool → database record created → user reviews in inbox → approval/rejection → tool activation.

## Approval Request Flow

### create_approval_request(server_id, source, context)

**Input**:
- `server_id` - ID of MCPServer record
- `source` - "agent" | "manual"
- `context` - Dict with reason (user message, etc.)

**Process**:
1. Create MCPToolApprovalRequest record with status="pending"
2. Update MCPServer.approval_requested_at
3. Return request record

**Output**: MCPToolApprovalRequest record

**Example**:
```python
context = {
    "tool_description": "I need to access my Notion databases",
    "registry_url": "https://github.com/.../notion",
    "agent_request": True,
}
await store.request_mcp_approval(server_id, source="agent", context=context)
```

### Approval Status Transitions

```
pending → approved (user clicks approve)
       → rejected  (user clicks reject)
```

### approve_mcp_server(server_id)

**Input**: `server_id` - MCPServer ID

**Process**:
1. Set MCPServer.approved = True
2. Set MCPServer.approved_at = now()
3. Mark all pending requests as "approved" with resolved_at = now()

**Output**: Updated MCPServer record

### reject_mcp_server(server_id)

**Input**: `server_id` - MCPServer ID

**Process**:
1. Delete MCPServer record (CASCADE deletes requests)
2. Mark all pending requests as "rejected" with resolved_at = now()

**Output**: None

### Inbox Integration

When MCPToolApprovalRequest is created:
- Record inserted into database
- Appears in pending_approval_requests() query
- UI fetches and displays to user
- User can approve/reject

## Tool Installation Request

### install_mcp_tool(tool_name, description="")

**Input**:
- `tool_name` - Tool name to install (e.g., "notion")
- `description` - Why you want it (optional)

**Process**:
1. Search registry for tool_name
2. If not found: return "not_found" status
3. If found:
   a. Check if already exists in database
   b. If approved: return "already_approved" status
   c. If pending: return "pending" status
   d. If new: create MCPServer + approval request
   e. return "requesting" status

**Output**: MCPToolInstallRequest
```python
class MCPToolInstallRequest(BaseModel):
    tool_name: str           # Name of the tool
    status: str              # "requesting" | "already_approved" | "not_found" | "pending"
    message: str             # Human-readable status
```

**Examples**:
```
User: "Install Notion"
→ {status: "requesting", message: "Requested permission..."}

User: "Install Notion" (again after approval)
→ {status: "already_approved", message: "The notion tools are already installed..."}

User: "Install xyz"
→ {status: "not_found", message: "Could not find 'xyz'..."}
```

## Testing

- [ ] Request creates database records
- [ ] Duplicate requests return pending status
- [ ] Approval updates database correctly
- [ ] Rejection marks requests as rejected
- [ ] Invalid tool names handled gracefully
