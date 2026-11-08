# System Prompt Loading Specification

## Overview

System prompt is loaded **once at agent pod startup** and included in every Claude API call during that session. On next pod restart, the latest version is reloaded from the database.

## Loading Flow

### 1. Agent Pod Startup

When the dash agent process starts:

```python
# In main agent initialization (e.g., main.py or agent.py)

async def initialize_agent():
    # ... other setup ...
    
    # Load system prompt from database
    config = await fetch_agent_config(user_id)
    system_prompt = config.system_prompt if config else ''
    
    # Store in agent context
    agent_context['system_prompt'] = system_prompt
    agent_context['system_prompt_loaded_at'] = datetime.utcnow()
    
    # Write to filesystem for debugging/introspection
    with open('/opt/data/dash.md', 'w') as f:
        f.write(system_prompt)
    
    logger.info(f'Loaded system prompt ({len(system_prompt)} chars)')
```

### 2. Kubernetes/Container Setup

**Agent Deployment** (`charts/dash/templates/agent/deployment.yaml`):
- Agent pod already has `/opt/data` mounted as PVC (`dash-agent-data`)
- `/opt/data` is writable by the agent process
- System prompt is written there as `/opt/data/dash.md` for easy inspection

**Volume Mount** (already exists):
```yaml
volumeMounts:
  - name: data
    mountPath: /opt/data
```

**No changes needed** to K8s deployment; we're just using existing volume.

### 3. API Call Construction

Every call to Claude includes **three layers of system instructions**:

```python
def build_system_message(user_id: str) -> str:
    # Layer 1: Base instructions (hardcoded, non-negotiable)
    layer_1 = '''You are dash, a personal AI agent built by Dash team.
Your purpose is to help the user automate and navigate their digital life.
Core capabilities: terminal execution, web access, file operations, memory, todo list.
Work systematically: break problems into steps, explain your reasoning, ask clarifying questions.'''
    
    # Layer 2: User customizations (from database)
    user_config = get_agent_config(user_id)
    layer_2 = user_config.system_prompt if user_config else ''
    
    # Layer 3 (optional): Pending suggestions (for transparency)
    layer_3 = ''
    if user_config and user_config.pending_system_prompt:
        layer_3 = f'''
[PENDING REVIEW - Not yet active]
Suggested addition to your system prompt:
{user_config.pending_system_prompt_context}

{user_config.pending_system_prompt}'''
    
    # Combine
    combined = f'{layer_1}\n\n{layer_2}'
    if layer_3:
        combined += f'\n\n{layer_3}'
    
    return combined
```

**In actual Claude API call:**
```python
response = client.messages.create(
    model='claude-opus-5-5',
    max_tokens=4096,
    system=build_system_message(user_id),  # ← includes all three layers
    messages=[...],  # user conversation
)
```

## Data Flow Diagram

```
[PostgreSQL agent_config]
         ↓
[Agent pod starts]
         ↓
[Query DB: SELECT system_prompt WHERE user_id = ?]
         ↓
[Store in memory + write to /opt/data/dash.md]
         ↓
[Every Claude API call reads from memory]
         ↓
[System message = Layer 1 + Layer 2]
         ↓
[User gets responses with correct context]
         ↓
        [Pod stays alive for session]
         ↓
[On pod restart: reload from DB again]
```

## Special Cases

### User Updates System Prompt (via API/UI)
1. User edits system prompt → PATCH /api/agent/system-prompt
2. Database updated
3. **Agent pod does NOT reload** (still running with old prompt)
4. Next pod restart: loads new version
5. **User can manually trigger pod restart** if urgent

### Agent Suggests Improvement
1. Agent calls suggest_system_prompt_update()
2. Creates inbox approval item
3. User reviews + approves
4. Approval moves pending → current
5. **Agent pod still uses old version** until restart
6. **Next pod restart: loads updated version**

### Empty System Prompt
- If user hasn't set system_prompt: defaults to empty string
- Layer 1 (base) is always included
- System still works (just without user customization)

### Pending Suggestion Exists
- Layer 3 is included in Claude API calls (marked as [PENDING REVIEW])
- Shows agent the suggestion is under review
- Provides transparency to user if they read conversation history
- Once approved, merges into Layer 2 and Layer 3 becomes empty

## Files

### Code Changes Required

1. **Agent initialization** (wherever dash agent starts)
   - Add: load system prompt from DB on startup
   - Add: write to /opt/data/dash.md
   - Add: store in agent context

2. **Claude API wrapper** (wherever API calls are made)
   - Update: build_system_message() to include all three layers
   - Pass combined message as `system` param

3. **Database query** (need helper function)
   - Get agent_config by user_id
   - Return system_prompt (or empty string)

### Kubernetes Changes

**None required** - agent pod already has writable `/opt/data` volume

### Configuration

No new config files needed. Reuses:
- Existing agent pod PVC (`dash-agent-data`)
- Existing PostgreSQL connection
- Existing user context

## Testing

### Unit Tests

```python
def test_build_system_message_includes_base():
    msg = build_system_message('user-123')
    assert 'You are dash' in msg

def test_build_system_message_includes_user_prompt():
    mock_config = AgentConfig(system_prompt='My custom context')
    msg = build_system_message('user-123')  # with mock
    assert 'My custom context' in msg

def test_build_system_message_includes_pending():
    mock_config = AgentConfig(
        system_prompt='Current',
        pending_system_prompt='Pending change'
    )
    msg = build_system_message('user-123')  # with mock
    assert 'PENDING REVIEW' in msg
    assert 'Pending change' in msg

def test_empty_system_prompt_works():
    mock_config = AgentConfig(system_prompt='')
    msg = build_system_message('user-123')
    assert 'You are dash' in msg
    assert len(msg) > 0
```

### Integration Tests

```python
def test_agent_loads_system_prompt_on_startup(agent_pod, db):
    # Create agent_config in DB
    config = AgentConfig(user_id=user_id, system_prompt='Test prompt')
    db.add(config)
    db.commit()
    
    # Start agent pod
    agent_pod.start()
    
    # Verify prompt was loaded
    dash_md = agent_pod.read_file('/opt/data/dash.md')
    assert 'Test prompt' in dash_md

def test_agent_includes_prompt_in_claude_call(agent, mock_claude_client):
    # Set up system prompt
    agent.system_prompt = 'Test context'
    
    # Make Claude call
    response = agent.call_claude_api(...)
    
    # Verify system message includes prompt
    call_args = mock_claude_client.messages.create.call_args
    system_msg = call_args.kwargs['system']
    assert 'Test context' in system_msg
    assert 'You are dash' in system_msg
```

## Performance Notes

- **Database query:** Happens once per pod start (minimal impact)
- **System prompt size:** Typically <10KB, negligible in API calls
- **Caching:** System prompt cached in memory for entire session (no repeated DB queries)
- **Latency:** <10ms to build system message on each API call
