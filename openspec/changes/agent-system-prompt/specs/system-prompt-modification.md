# System Prompt Modification Specification

## Overview

System prompt can be modified in two ways:
1. **User modifies** via UI/API (direct update)
2. **Agent suggests** via tool call (requires approval)

## User-Initiated Modification

### API: PATCH /api/agent/system-prompt

Update the system prompt directly.

**Endpoint:** `PATCH /api/agent/system-prompt`

**Authentication:** Required (user context)

**Request Body:**
```json
{
  "content": "You are dash, a personal AI agent...

Special context about my projects..."
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "system_prompt": "[full prompt that was saved]",
  "updated_at": "2024-10-24T14:30:00Z",
  "updated_by": "[user_id]"
}
```

**Response (401 Unauthorized):**
```json
{
  "error": "Authentication required"
}
```

**Response (400 Bad Request):**
```json
{
  "error": "content field is required",
  "fields": ["content"]
}
```

**Database Changes:**
```python
config = get_agent_config(current_user.id)
config.system_prompt = request.json['content']
config.system_prompt_updated_at = datetime.utcnow()
config.system_prompt_updated_by = current_user.id

# Clear any pending suggestion (user is manually updating)
if config.pending_system_prompt:
    config.pending_system_prompt = None
    config.pending_system_prompt_context = None
    config.pending_system_prompt_created_at = None
    # Dismiss inbox item if it exists
    if config.pending_system_prompt_inbox_id:
        inbox_item = db.query(InboxItem).filter_by(
            id=config.pending_system_prompt_inbox_id
        ).first()
        if inbox_item:
            inbox_item.status = 'dismissed'
        config.pending_system_prompt_inbox_id = None

db.session.commit()
```

**Side Effects:**
- Clears any pending agent suggestion (user takes control)
- Dismisses related inbox item if exists
- Updates `updated_at` timestamp
- Does NOT restart agent pod (changes take effect on next pod restart)

---

## Agent-Initiated Modification (Suggestion)

### Tool: `suggest_system_prompt_update()`

Agent proposes a change to its system prompt.

**Function Signature:**
```python
def suggest_system_prompt_update(
    content: str,
    context: str
) -> dict:
    """
    Suggest an update to the system prompt.
    
    Args:
        content: New or modified system prompt (full text or change description)
        context: Explanation of why this would help (user-visible in inbox)
    
    Returns:
        {
            "status": "created",
            "request_id": "uuid",
            "user_notified": true,
            "content_preview": "First 100 chars..."
        }
    
    Raises:
        PermissionError: if user has disabled agent suggestions
        ValueError: if content or context is empty
    """
```

**Agent Usage Example:**
```python
# Agent discovers codebase structure
codebase_info = analyze_codebase()

# Suggests improvement
result = suggest_system_prompt_update(
    content=f"""{current_system_prompt}

## Codebase Structure
- Language: Python
- Architecture: Monorepo with {codebase_info['num_packages']} packages
- Package manager: uv
- Test framework: pytest
""",
    context="I analyzed your codebase and discovered key architectural patterns. This context will help me make better decisions about code generation and recommendations."
)

agent.log(f"System prompt improvement suggested: {result['request_id']}")
```

### Implementation

**API Endpoint:** `POST /api/agent/system-prompt/suggest`

**Request Body:**
```json
{
  "content": "Full system prompt text including the suggestion",
  "context": "Why this would help (shown to user in inbox)"
}
```

**Response (201 Created):**
```json
{
  "status": "created",
  "request_id": "uuid-xyz",
  "user_notified": true,
  "created_at": "2024-10-24T15:00:00Z",
  "content_preview": "Current prompt + new sections: [...first 200 chars...]"
}
```

**Error Cases:**

```json
// 400: Empty content
{
  "error": "content cannot be empty",
  "field": "content"
}
```

```json
// 400: Content too long (e.g., >50KB)
{
  "error": "content exceeds maximum length",
  "max_length": 50000
}
```

```json
// 400: No change (content same as current)
{
  "error": "suggested content is identical to current",
  "status": "no_change"
}
```

```json
// 403: User disabled suggestions
{
  "error": "system prompt suggestions are disabled",
  "status": "disabled"
}
```

```json
// 409: Already has pending suggestion
{
  "error": "suggestion already pending approval",
  "pending_request_id": "uuid-abc",
  "status": "pending"
}
```

**Database Changes:**
```python
config = get_agent_config(agent_user_id)

# Reject if user disabled suggestions
if config.suggestions_disabled:
    raise PermissionError("suggestions disabled")

# Reject if already pending
if config.pending_system_prompt:
    raise ConflictError("suggestion already pending")

# Reject if identical
if content == config.system_prompt:
    raise ValueError("content is identical")

# Create suggestion
config.pending_system_prompt = content
config.pending_system_prompt_context = context
config.pending_system_prompt_created_at = datetime.utcnow()

# Create inbox item
inbox_item = InboxItem(
    user_id=agent_user_id,
    type='system_prompt_approval',
    title='Agent Suggests System Prompt Update',
    content={
        'current_prompt': config.system_prompt,
        'suggested_prompt': content,
        'agent_context': context,
        'request_id': str(config.id)
    },
    action_required=True,
)
db.session.add(inbox_item)
db.session.flush()

config.pending_system_prompt_inbox_id = inbox_item.id
db.session.commit()

return {
    'status': 'created',
    'request_id': str(config.id),
    'user_notified': True,
    'created_at': config.pending_system_prompt_created_at.isoformat(),
}
```

---

## Approval Workflow (User Review)

### API: POST /api/agent/system-prompt/approve

User approves pending suggestion.

**Endpoint:** `POST /api/agent/system-prompt/approve`

**Authentication:** Required (user context)

**Request Body:**
```json
{
  "request_id": "uuid"
}
```

**Response (200 OK):**
```json
{
  "status": "approved",
  "new_system_prompt": "[full merged prompt]",
  "approved_at": "2024-10-24T15:30:00Z",
  "approved_by": "[user_id]",
  "note": "Changes take effect on next agent pod restart"
}
```

**Error Cases:**

```json
// 404: No pending suggestion
{
  "error": "no pending suggestion to approve",
  "status": "not_found"
}
```

**Database Changes:**
```python
config = get_agent_config(current_user.id)

if not config.pending_system_prompt:
    raise NotFoundError("no pending suggestion")

# Move pending to current
config.system_prompt = config.pending_system_prompt
config.system_prompt_updated_at = datetime.utcnow()
config.system_prompt_updated_by = current_user.id

# Clear pending
config.pending_system_prompt = None
config.pending_system_prompt_context = None
config.pending_system_prompt_created_at = None

# Mark inbox item as resolved
if config.pending_system_prompt_inbox_id:
    inbox_item = db.query(InboxItem).filter_by(
        id=config.pending_system_prompt_inbox_id
    ).first()
    if inbox_item:
        inbox_item.status = 'resolved'
        inbox_item.action_required = False
    config.pending_system_prompt_inbox_id = None

db.session.commit()
```

### API: POST /api/agent/system-prompt/reject

User rejects pending suggestion.

**Endpoint:** `POST /api/agent/system-prompt/reject`

**Authentication:** Required (user context)

**Request Body:**
```json
{
  "request_id": "uuid",
  "reason": "Not relevant at this time"
}
```

**Response (200 OK):**
```json
{
  "status": "rejected",
  "rejected_at": "2024-10-24T15:30:00Z",
  "reason": "Not relevant at this time"
}
```

**Database Changes:**
```python
config = get_agent_config(current_user.id)

if not config.pending_system_prompt:
    raise NotFoundError("no pending suggestion")

# Clear pending
config.pending_system_prompt = None
config.pending_system_prompt_context = None
config.pending_system_prompt_created_at = None

# Mark inbox item as rejected
if config.pending_system_prompt_inbox_id:
    inbox_item = db.query(InboxItem).filter_by(
        id=config.pending_system_prompt_inbox_id
    ).first()
    if inbox_item:
        inbox_item.status = 'rejected'
        inbox_item.action_required = False
    config.pending_system_prompt_inbox_id = None

db.session.commit()
```

---

## State Transitions

```
[No pending] ←──────────────────────────────┐
     │                                        │
     ├─→ Agent calls suggest()                │
     │                                        │
[Pending] ─→ User clicks Approve ──→ Merged to current
     │                                    ↓
     └──→ User clicks Reject ──────→ Cleared
```

## Constraints

- **One pending at a time:** Only one suggestion can be pending per user
- **Can't suggest same content:** Agent can't suggest what's already current
- **Suggestions are transient:** If user manually updates, pending is dismissed
- **Inbox linked:** Suggestion must have an inbox_item associated
- **Content limits:** Suggested content can't exceed 50KB

## Security

- **Authentication required** for all modifications
- **User isolation:** Users can only modify their own system prompt
- **Audit trail:** system_prompt_updated_by and pending_system_prompt_created_at tracked
- **Tool availability:** Only agent can call suggest(); users use API/UI
- **Permissions:** User can disable suggestions if desired
