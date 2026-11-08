# Implementation Tasks

## PR 1: Database Schema

- [ ] Create migration: `agent_config` table
  - [ ] id (UUID PK)
  - [ ] user_id (FK to users)
  - [ ] system_prompt (TEXT, default empty)
  - [ ] system_prompt_updated_at / updated_by
  - [ ] pending_system_prompt (TEXT, nullable)
  - [ ] pending_system_prompt_context (TEXT, nullable)
  - [ ] pending_system_prompt_created_at
  - [ ] pending_system_prompt_inbox_id (FK to inbox_items, nullable)
  - [ ] created_at / updated_at
- [ ] Create seed/fixture for testing: one user with sample system prompt
- [ ] Add index: agent_config(user_id)

**Spec:** `specs/system-prompt-storage.md`

---

## PR 2: API Endpoints (User Updates)

### Endpoints to implement:
- [ ] `GET /api/agent/system-prompt` 
  - Returns: `{ system_prompt, pending_system_prompt, pending_context }`
  - Auth: user must own the agent_config
  
- [ ] `PATCH /api/agent/system-prompt`
  - Body: `{ content: string }`
  - Updates: system_prompt, system_prompt_updated_at, system_prompt_updated_by
  - Side effect: Clears pending_system_prompt if user is manually updating
  - Response: `{ success, updated_at }`

- [ ] `POST /api/agent/system-prompt/reject`
  - Rejects pending suggestion
  - Clears pending_system_prompt + pending_context + pending_inbox_id
  - Returns: `{ rejected: true }`

### Tests:
- [ ] Unauthenticated request returns 401
- [ ] User can only read/update their own system prompt
- [ ] Manual update clears pending suggestion
- [ ] API returns current state

**Spec:** `specs/system-prompt-loading.md`

---

## PR 3: Agent Pod Integration

### Changes:
- [ ] On agent pod startup (wherever dash agent initializes):
  - [ ] Query DB: `SELECT system_prompt FROM agent_config WHERE user_id = ?`
  - [ ] Write to `/opt/data/dash.md` (or read from there if already exists)
  - [ ] Load into agent context/memory for use in prompts

- [ ] Update Claude API call construction:
  - [ ] Layer 1: [hardcoded base instructions]
  - [ ] Layer 2: [read from /opt/data/dash.md]
  - [ ] Combine and pass as system message

- [ ] Kubernetes: ensure agent pod can write to `/opt/data` (already has dash-agent-data PVC)

### Tests:
- [ ] Agent pod can read system prompt from DB
- [ ] Claude API call includes both Layer 1 + Layer 2
- [ ] If system_prompt is empty, Layer 2 is empty string (no error)
- [ ] Pod restart reloads latest prompt from DB

**Spec:** `specs/system-prompt-loading.md`

---

## PR 4: Agent Tools

### Tools to implement:

#### `get_system_prompt() -> str`
- [ ] Returns current system prompt (from /opt/data/dash.md or memory)
- [ ] Agent can use to introspect its own instructions
- [ ] No parameters
- [ ] Returns: full text of current system prompt

#### `suggest_system_prompt_update(content: str, context: str) -> dict`
- [ ] Parameters:
  - [ ] content: new system prompt (or modifications)
  - [ ] context: explanation of why (shown to user in inbox)
- [ ] Calls API: POST /api/agent/system-prompt/suggest
- [ ] Creates inbox approval request
- [ ] Returns: `{ status: "created", request_id: uuid, user_notified: true }`

### Tests:
- [ ] Agent can call get_system_prompt() and receive result
- [ ] Agent can call suggest_system_prompt_update()
- [ ] Suggestion creates DB entry + inbox item
- [ ] Agent receives confirmation of request creation

**Spec:** `specs/system-prompt-modification.md`

---

## PR 5: Inbox Integration

### Changes:
- [ ] Implement `POST /api/agent/system-prompt/approve` endpoint
  - [ ] Requires inbox approval context
  - [ ] Merges pending_system_prompt into system_prompt
  - [ ] Clears pending fields
  - [ ] Updates system_prompt_updated_by (set to approver)
  - [ ] Clears pending_system_prompt_inbox_id
  - [ ] Returns: `{ approved: true, updated_content }`

- [ ] Inbox item template for system prompt suggestions:
  - [ ] Shows current system prompt
  - [ ] Shows proposed changes
  - [ ] Shows agent's context/justification
  - [ ] Has Approve/Reject buttons

- [ ] Integration:
  - [ ] When agent calls suggest_system_prompt_update(), create inbox item
  - [ ] Inbox item links to approval endpoints
  - [ ] On approve: call endpoint, update DB, confirm to user
  - [ ] On reject: call endpoint, dismiss from inbox

### Tests:
- [ ] Suggestion creates visible inbox item
- [ ] User can approve suggestion
- [ ] User can reject suggestion
- [ ] Approved suggestion merges into system_prompt
- [ ] Rejected suggestion is discarded
- [ ] Approved change takes effect on next agent pod start

**Spec:** `specs/system-prompt-modification.md`

---

## PR 6: UI Dashboard (Optional, may be separate team)

- [ ] Dashboard page: Agent Settings → System Prompt
- [ ] Display current system_prompt text
- [ ] Textarea for editing
- [ ] Save button → calls PATCH /api/agent/system-prompt
- [ ] Show pending suggestions if any
  - [ ] Display agent's proposal + context
  - [ ] Manual Approve/Reject buttons
- [ ] Show history/audit trail (optional enhancement)

---

## Testing Strategy

### Unit Tests:
- [ ] API endpoint auth + authorization
- [ ] Database state transitions (pending → approved)
- [ ] System prompt loading on agent startup

### Integration Tests:
- [ ] Full workflow: User updates → Pod restart → Agent loads
- [ ] Full workflow: Agent suggests → Inbox → User approves → Takes effect
- [ ] Reject workflow: Agent suggests → User rejects → Cleared

### E2E Tests:
- [ ] User edits system prompt in UI → Agent sees change on next run
- [ ] Agent suggests change → User approves → Works on next turn
