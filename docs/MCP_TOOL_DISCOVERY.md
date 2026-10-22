# MCP Tool Discovery and Approval

This feature allows the agent to discover, request, and install new MCP (Model Context Protocol) tools dynamically through chat, with your approval.

## How It Works

### 1. Agent Requests Tool Installation

In chat, you can ask the agent to install MCP tools:

```
"Please install the Notion MCP tools so I can manage my databases"
"Can you add GitHub tools?"
"Install the Linear MCP tool"
```

### 2. Discovery Process

When you request a tool:
- The agent searches the [public MCP registry](https://github.com/modelcontextprotocol/servers)
- Finds the matching tool and its description
- Creates an approval request
- Notifies you to review in your inbox

### 3. Review and Approval

An inbox item appears showing:
- Tool name and description
- Why the agent requested it (context from your message)
- Link to the GitHub repository
- Approve/Reject buttons

### 4. Installation

Once approved:
- The tool is marked as active in the database
- The agent loads it on the next turn
- Tools are immediately usable by the agent

## Using the Tools in Chat

### Search for Tools

```
Agent tool: search_mcp_tools(query="notion")
```

Returns a list of matching tools from the registry.

### Install a Tool

```
Agent tool: install_mcp_tool(tool_name="notion")
```

Returns:
- `status: "requesting"` - Approval request sent, awaiting your review
- `status: "already_approved"` - Tool is already installed
- `status: "not_found"` - Tool doesn't exist in the registry
- `status: "pending"` - Request already pending

## Architecture

### Database Schema

**mcp_servers** table:
- `id` - Auto-incrementing primary key
- `name` - Tool name (e.g., "notion")
- `url` - GitHub repository URL
- `description` - What this tool does
- `approved` - Boolean, is it enabled?
- `approval_requested_at` - When the first request was made
- `approved_at` - When it was approved
- `created_at` - When the record was created

**mcp_tool_approval_requests** table:
- `id` - Auto-incrementing primary key
- `mcp_server_id` - Foreign key to mcp_servers
- `source` - "agent" or "manual"
- `request_context` - JSON context (why the tool was requested)
- `status` - "pending", "approved", or "rejected"
- `created_at` - When requested
- `resolved_at` - When it was reviewed

### Key Components

**registry.py** - Discovers tools from the public MCP registry
**mcp_tools.py** - Agent tools for discovery and installation
**mcp_config.py** - Loads approved tools into the engine

## Future Enhancements

- Per-tool exclusion rules (install a server but exclude certain tools)
- Tool configuration parameters stored in the database
- Approval history and audit trail
- Scheduled tool updates
- Custom registry support
