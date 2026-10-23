# Agent System Prompt Configuration - Design

## Architecture

### Three-Layer System Prompt

```
API Call to Claude:
  ├── Layer 1 (Hardcoded):
  │   """You are dash, a personal AI agent..."""
  │
  ├── Layer 2 (User-configurable):
  │   [content from DB agent_config.system_prompt]
  │
  └── Layer 3 (Pending improvements):
      [if agent has pending suggestion, optionally include for transparency]
```

### Data Flow

```
┌─────────────────────────────────────────────────────┐
│ PostgreSQL (agent_config table)                     │
│ ├── system_prompt: TEXT (current user instructions) │
│ ├── pending_system_prompt: TEXT (agent suggestion)  │
│ └── pending_system_prompt_context: TEXT (why)       │
└──────────────────┬──────────────────────────────────┘
                   │
                   ├─→ Agent Pod (on startup)
                   │   ├── Query DB
                   │   ├── Mount to /opt/data/dash.md
                   │   └── Include in Claude system prompt
                   │
                   └─→ API Layer
                       ├── GET /api/agent/system-prompt (read current)
                       ├── PATCH /api/agent/system-prompt (user update)
                       └── POST /api/agent/system-prompt/suggest (agent propose)
```

### Database Schema

```sql
CREATE TABLE agent_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    
    -- Layer 2: User system prompt
    system_prompt TEXT DEFAULT '',
    system_prompt_updated_at TIMESTAMP,
    system_prompt_updated_by UUID REFERENCES users(id),
    
    -- Layer 3: Pending agent improvements
    pending_system_prompt TEXT,
    pending_system_prompt_context TEXT,  -- Why agent suggests this
    pending_system_prompt_created_at TIMESTAMP,
    pending_system_prompt_inbox_id UUID REFERENCES inbox_items(id),
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Agent Pod Mounting

**On startup:**
1. Query DB: `SELECT system_prompt FROM agent_config WHERE user_id = ?`
2. Write to filesystem: `/opt/data/dash.md`
3. Include in Claude system message when making API calls

**Kubernetes deployment** (agent/deployment.yaml):
- Agent pod already has `/opt/data` (dash-agent-data PVC) mounted as writable
- On startup: dash code reads from DB and writes `/opt/data/dash.md`
- On each Claude call: read from `/opt/data/dash.md` to include in system prompt

### API Endpoints

#### GET /api/agent/system-prompt
- Returns current system_prompt + pending_system_prompt (if any)
- Used by: UI dashboard, agent itself

#### PATCH /api/agent/system-prompt
- Updates system_prompt in DB
- Params: `{ content: string }`
- Called by: UI dashboard (user editing)
- Clears any pending suggestion if user manually updates

#### POST /api/agent/system-prompt/suggest
- Agent proposes a change
- Params: `{ content: string, context: string }`
- Stores in pending_system_prompt
- Creates inbox approval request
- Called by: agent (via tool call)

#### POST /api/agent/system-prompt/approve
- Human approves pending suggestion
- Merges pending into system_prompt
- Clears pending fields
- Creates audit trail
- Called by: inbox approval handler

#### POST /api/agent/system-prompt/reject
- Human rejects pending suggestion
- Clears pending fields
- Called by: inbox approval handler

### Agent Tools

Agent has two new tools:

#### 1. `get_system_prompt()`
```python
def get_system_prompt() -> str:
    """Get the current system prompt (dash.md) being used by this agent."""
    # Reads from /opt/data/dash.md or queries API
    # Used by agent to understand its own context/instructions
```

#### 2. `suggest_system_prompt_update(content: str, context: str) -> dict`
```python
def suggest_system_prompt_update(content: str, context: str) -> dict:
    """Suggest an update to the system prompt with justification.
    
    Args:
        content: New or modified system prompt text
        context: Why this change would help (shown to human in inbox)
    
    Returns:
        { status: "created", request_id: "...", user_notified: true }
    """
    # Calls POST /api/agent/system-prompt/suggest
    # Creates inbox item for user review
```

### Loading Strategy

**Timing:** Agent loads system prompt **once on startup**
- Query DB immediately after connecting
- Write to local `/opt/data/dash.md`
- Include in every Claude API call for that session
- On next pod restart: reloads from DB

**Why not per-turn?** 
- Reduces database queries
- Keeps system instructions stable during a conversation
- User changes take effect on next pod restart (acceptable latency)
- If urgent, user can trigger pod restart from dashboard

### Backward Compatibility

- If no row in `agent_config`: system_prompt defaults to empty string (Layer 2 is optional)
- Layer 1 (base instructions) always present in every API call
- Existing agents without a system_prompt continue working (just Layer 1)

## Security

- System prompt stored in DB, accessed like any other configuration
- Only authenticated users can read/update their own system_prompt
- Audit trail: who updated when (updated_by, updated_at fields)
- Pending suggestions require human approval before taking effect
- Agent cannot bypass approval workflow (only calls POST /suggest, not PATCH)

## Implementation Order

1. **PR 1: Database Schema** - Create agent_config table
2. **PR 2: API Endpoints** - Read + update endpoints (user-only)
3. **PR 3: Agent Pod Integration** - Load system prompt on startup
4. **PR 4: Agent Tools** - get_system_prompt() + suggest_system_prompt_update()
5. **PR 5: Inbox Integration** - Approval workflow for suggestions
6. **PR 6: UI Dashboard** - User editing interface (optional, separate team)
