# Agent System Prompt Configuration (dash.md)

## Problem

Currently, the agent's system instructions are static—either hardcoded in API calls or baked into Docker images. Users have no way to:
1. Customize the agent's personality, context, or capabilities
2. Add domain-specific instructions relevant to their workflows
3. Teach the agent about their conventions and preferences
4. Persist those learnings across sessions

Additionally, developers need a way to define core system instructions that shouldn't be overridden.

## Solution

Implement a **three-layer system prompt architecture**:

1. **Layer 1: Developer Base Instructions** (hardcoded)
   - Built into every API call to Claude
   - "You are dash, a personal AI agent..."
   - Non-negotiable foundation set by Dash team

2. **Layer 2: User System Prompt (dash.md)** (configurable)
   - Stored in PostgreSQL
   - Mounted to agent pod on startup
   - User edits via UI dashboard
   - Persists across pod restarts and agent runs

3. **Layer 3: Agent Self-Improvement** (optional, with approval)
   - Agent suggests improvements to its own system prompt
   - Creates approval request in inbox
   - Human reviews and approves/rejects
   - Approved changes merge into user system prompt

## User Flow

### Basic Configuration
```
User: Opens Dash dashboard → Agent Settings → System Prompt
  ↓
Edits dash.md content (e.g., "Add context about my project structure")
  ↓
Saves to database
  ↓
On next agent pod restart: reads updated dash.md from DB
  ↓
Claude API call includes Layer 1 (base) + Layer 2 (user) instructions
```

### Self-Improvement (Optional)
```
Agent: "I should add this to understand your codebase better: [suggestion]"
  ↓
Calls agent API: POST /api/agent/system-prompt/suggest
  ↓
Creates inbox request: pending_system_prompt in DB
  ↓
User sees in inbox, reviews suggestion, clicks Approve
  ↓
On approval: suggestion merges into system_prompt
  ↓
Next agent turn: uses updated system prompt
```

## Key Benefits

- **User control** - Personalize agent behavior without code changes
- **Developer safety** - Base instructions always present, can't be removed
- **Self-improvement** - Agent can learn and suggest improvements
- **Transparency** - All changes reviewed and auditable
- **Persistence** - Settings survive pod restarts
- **Simple** - No new services needed (uses existing DB)

## Scope

This feature includes:
- Database schema for system prompt storage
- Agent pod ConfigMap/volume mounting strategy
- API endpoints for reading/updating system prompt
- Agent tools for suggesting changes + querying current prompt
- Integration with inbox approval system
- Claude API prompt construction (Layer 1 + Layer 2 + Layer 3)

Out of scope:
- UI dashboard for editing (handled by separate Dash UI PR)
- System prompt versioning/history (future enhancement)
- Role-based access control for system prompt (future enhancement)
