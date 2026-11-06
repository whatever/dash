# Agent MCP Tool Discovery and Approval

## Problem

Currently, MCP tools must be manually configured via environment variables before the agent starts. Users can't dynamically add new tools through chat, and there's no approval workflow for tooling decisions.

## Solution

Enable the agent to:
1. **Discover** MCP tools from the [public registry](https://github.com/modelcontextprotocol/servers)
2. **Request** approval to install them (agent-initiated)
3. **Receive approval** through the inbox system
4. **Persist** approved tools in the database
5. **Use** newly approved tools on subsequent turns

## User Flow

```
User: "Please install Notion MCP tools"
  ↓
Agent: Searches registry, finds matching tool
  ↓
Creates approval request in database
  ↓
Inbox notification appears for user review
  ↓
User approves/rejects in inbox
  ↓
If approved: Tool is marked active, loaded on next agent turn
```

## Key Benefits

- **Dynamic tooling** - No restart needed to add new tools
- **User control** - All tool installations require explicit approval
- **Discoverable** - Agents can search available tools
- **Persistent** - Approved tools survive restarts
- **Auditable** - Approval requests stored with context

## Scope

This feature includes:
- MCP server discovery from public registry
- Database schema for servers and approval requests
- Agent tools for install + search
- Integration with inbox approval system
- Database persistence layer

Out of scope:
- UI for approval (uses existing inbox system)
- Per-tool exclusion rules (future enhancement)
- Custom registry support (future enhancement)
