# System Prompt Storage Specification

## Database Schema

### Table: `agent_config`

Stores per-user agent configuration including system prompt and improvement suggestions.

```sql
CREATE TABLE agent_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    
    -- Layer 2: User-configurable system prompt (dash.md)
    system_prompt TEXT DEFAULT '',
    system_prompt_updated_at TIMESTAMP DEFAULT NOW(),
    system_prompt_updated_by UUID REFERENCES users(id),
    
    -- Layer 3: Pending agent-suggested improvements (awaiting approval)
    pending_system_prompt TEXT,
    pending_system_prompt_context TEXT,
    pending_system_prompt_created_at TIMESTAMP,
    pending_system_prompt_inbox_id UUID REFERENCES inbox_items(id) ON DELETE SET NULL,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_agent_config_user_id ON agent_config(user_id);
```

### Field Descriptions

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| id | UUID | gen_random_uuid() | Primary key |
| user_id | UUID | - | Reference to users table (UNIQUE) |
| system_prompt | TEXT | '' | Current system instructions for agent (Layer 2) |
| system_prompt_updated_at | TIMESTAMP | NOW() | When system_prompt was last changed |
| system_prompt_updated_by | UUID | NULL | Which user (usually user_id, or admin if edited) |
| pending_system_prompt | TEXT | NULL | Agent's proposed new/modified system prompt |
| pending_system_prompt_context | TEXT | NULL | Why agent suggests this change |
| pending_system_prompt_created_at | TIMESTAMP | NULL | When suggestion was created |
| pending_system_prompt_inbox_id | UUID | NULL | Link to inbox approval item |
| created_at | TIMESTAMP | NOW() | When this config was created |
| updated_at | TIMESTAMP | NOW() | When this config was last updated |

## Initialization

### On User Creation
When a new user is created, an agent_config row is automatically created:

```python
# In user creation handler:
agent_config = AgentConfig(
    user_id=new_user.id,
    system_prompt='',  # Empty initially, user fills in later
)
db.session.add(agent_config)
db.session.commit()
```

### Migration

```python
# In migrations/XXX_add_agent_config.py

def upgrade():
    op.create_table(
        'agent_config',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('system_prompt', sa.Text(), server_default=''),
        sa.Column('system_prompt_updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('system_prompt_updated_by', sa.UUID(), nullable=True),
        sa.Column('pending_system_prompt', sa.Text(), nullable=True),
        sa.Column('pending_system_prompt_context', sa.Text(), nullable=True),
        sa.Column('pending_system_prompt_created_at', sa.DateTime(), nullable=True),
        sa.Column('pending_system_prompt_inbox_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['system_prompt_updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['pending_system_prompt_inbox_id'], ['inbox_items.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_index('idx_agent_config_user_id', 'agent_config', ['user_id'])

def downgrade():
    op.drop_index('idx_agent_config_user_id', 'agent_config')
    op.drop_table('agent_config')
```

## Data States

### Normal State (User has edited system prompt)
```json
{
  "user_id": "uuid-123",
  "system_prompt": "You are dash, a personal AI agent...[user's custom instructions]",
  "system_prompt_updated_at": "2024-10-24T12:00:00Z",
  "system_prompt_updated_by": "uuid-123",
  "pending_system_prompt": null,
  "pending_system_prompt_context": null,
  "pending_system_prompt_created_at": null,
  "pending_system_prompt_inbox_id": null
}
```

### With Pending Suggestion (Agent has proposed change)
```json
{
  "user_id": "uuid-123",
  "system_prompt": "[previous instructions]",
  "system_prompt_updated_at": "2024-10-20T12:00:00Z",
  "system_prompt_updated_by": "uuid-123",
  "pending_system_prompt": "[previous instructions + new section about codebase]",
  "pending_system_prompt_context": "I discovered your project uses a monorepo pattern; I should understand this",
  "pending_system_prompt_created_at": "2024-10-24T14:00:00Z",
  "pending_system_prompt_inbox_id": "inbox-uuid-456"
}
```

## Constraints

- **One config per user:** `user_id` is UNIQUE
- **Cascading delete:** If user is deleted, their agent_config is deleted
- **Pending requires context:** If pending_system_prompt is set, pending_system_prompt_context must also be set
- **No orphaned inbox links:** If inbox_item is deleted, pending_system_prompt_inbox_id is set to NULL

## Queries

### Get agent config for user
```python
config = db.session.query(AgentConfig).filter_by(user_id=user_id).first()
```

### Get system prompt for Claude API call
```python
system_prompt = config.system_prompt if config else ''
```

### Get pending suggestions awaiting approval
```python
pending = db.session.query(AgentConfig).filter(
    AgentConfig.user_id == user_id,
    AgentConfig.pending_system_prompt.isnot(None)
).first()
```

### Approve pending suggestion
```python
config.system_prompt = config.pending_system_prompt
config.system_prompt_updated_at = datetime.utcnow()
config.system_prompt_updated_by = approver_user_id
config.pending_system_prompt = None
config.pending_system_prompt_context = None
config.pending_system_prompt_created_at = None
config.pending_system_prompt_inbox_id = None
db.session.commit()
```

### Reject pending suggestion
```python
config.pending_system_prompt = None
config.pending_system_prompt_context = None
config.pending_system_prompt_created_at = None
config.pending_system_prompt_inbox_id = None
db.session.commit()
```
