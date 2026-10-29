# Artifacts System - Design

## Architecture Overview

```
┌──────────────────┐
│   Browser        │
│                  │
│  ┌────────────┐  │
│  │ Chat UI    │  │  GET /api/jobs/{id}/events (SSE)
│  │            │◄─┼──────────────────────────┐
│  └─────┬──────┘  │                          │
│        │         │                          │
│        │ iframe: │                          │
│        │ /artifacts/{id}/preview            │
│        │         │                          │
└────────┼─────────┘                          │
         │                                    │
         │                                    │
    ┌────▼──────────────────────────┐        │
    │  Artifacts Service (new pod)  │        │
    │                               │        │
    │  GET /{id}/preview            │        │
    │  POST /api/artifacts          │◄───┐   │
    │  POST /{id}/versions          │    │   │
    │  GET /api/artifacts           │    │   │
    └──────────┬────────────────────┘    │   │
               │                         │   │
               │                         │   │
    ┌──────────▼────────────────────┐   │   │
    │  Dash Worker                  │   │   │
    │                               │   │   │
    │  - Parses <artifact> tags     │───┘   │
    │  - Creates artifacts          │       │
    │  - Emits events to Redis      │───────┘
    └──────────┬────────────────────┘
               │
    ┌──────────▼────────────────────┐
    │  Postgres (shared)            │
    │                               │
    │  - artifacts                  │
    │  - artifact_versions          │
    │  - conversations              │
    │  - messages                   │
    └───────────────────────────────┘
```

## Database Schema

### artifacts table

```sql
CREATE TABLE artifacts (
    id TEXT PRIMARY KEY,  -- nanoid: 'proposal-abc123'
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    type TEXT NOT NULL,  -- 'html', 'markdown', 'react'
    current_version INTEGER NOT NULL DEFAULT 1,
    visibility TEXT NOT NULL DEFAULT 'organization',  -- 'private', 'organization', 'public'
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX idx_artifacts_conversation ON artifacts(conversation_id);
CREATE INDEX idx_artifacts_created_at ON artifacts(created_at DESC);
```

### artifact_versions table

```sql
CREATE TABLE artifact_versions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    message_id BIGINT REFERENCES messages(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    UNIQUE(artifact_id, version)
);

CREATE INDEX idx_artifact_versions_artifact ON artifact_versions(artifact_id, version DESC);
```

## Message Event Schema

Artifacts are represented as events in the `messages.events` JSONB array:

```python
{
    "kind": "artifact",
    "id": "proposal-abc123",
    "title": "OpenSpec: Artifacts System",
    "type": "markdown",
    "version": 1,
    "url": "/artifacts/proposal-abc123/preview"
}
```

## Agent Protocol

Hermes uses XML-like tags to signal artifact creation:

```xml
<artifact type="markdown" title="OpenSpec: Artifacts System">
# Artifacts System

## Problem
...
</artifact>
```

**Tag attributes:**
- `type` (required): 'html', 'markdown', 'react'
- `title` (required): Human-readable title
- `id` (optional): For updates, references existing artifact

**Example update:**
```xml
<artifact id="proposal-abc123" type="markdown" title="OpenSpec: Artifacts System">
# Artifacts System

## Problem
...

## Security Considerations
(new section added)
</artifact>
```

## API Endpoints

### Internal API (called by worker)

**POST /api/artifacts**
```json
{
  "type": "markdown",
  "title": "OpenSpec: Artifacts System",
  "content": "# Artifacts...",
  "conversation_id": "uuid",
  "message_id": 12345
}

Response: 201
{
  "id": "proposal-abc123",
  "version": 1
}
```

**POST /api/artifacts/{id}/versions**
```json
{
  "content": "# Updated content...",
  "message_id": 12346
}

Response: 200
{
  "version": 2
}
```

### Public API (called by browser)

**GET /artifacts/{id}/preview**
- Renders HTML (with auth check)
- Returns 200 with HTML or 404

**GET /api/artifacts?conversation_id={uuid}**
- Lists artifacts for conversation
- Returns array of artifact metadata

**GET /api/artifacts/{id}/raw**
- Returns source content for editing
- Returns `{id, title, type, content, version}`

**PATCH /api/artifacts/{id}**
- Update visibility/metadata
- Body: `{visibility: 'public'}`

## Permissions Model

### V1: Organization-based (simple)

- All artifacts created by org members visible to org
- Artifact ID is unguessable (nanoid: 21 chars, URL-safe)
- `visibility` field for future use

### V2: Explicit ACLs (future)

Add `artifact_permissions` table:
```sql
CREATE TABLE artifact_permissions (
    artifact_id TEXT REFERENCES artifacts(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    permission TEXT NOT NULL,  -- 'view', 'edit'
    PRIMARY KEY (artifact_id, user_id)
);
```

## Rendering Strategy

### Markdown
- Server-side render to HTML
- Apply styling consistent with dash UI
- Sanitize content

### HTML
- Serve in sandboxed iframe
- CSP headers to prevent XSS
- No external script loading in V1

### React (future)
- Bundle with preact + htm
- Render client-side in iframe

## Worker Integration

```python
# In worker.py handle_chat()

async def handle_chat(self, job: Job) -> None:
    # ... existing code ...
    
    async for delta in self.chat.stream(conversation, user_text, instructions):
        # Check if delta contains artifact tags
        if "<artifact" in delta.text:
            artifact_data = parse_artifact_tag(delta.text)
            artifact = await create_artifact(artifact_data)
            await emit("artifact", 
                id=artifact.id,
                title=artifact.title,
                type=artifact.type,
                version=artifact.version
            )
        # ... rest of existing code ...
```

## Deployment

Add to `charts/dash/values.yaml`:
```yaml
artifacts:
  enabled: true
  replicas: 2
  resources:
    requests: { cpu: 100m, memory: 256Mi }
    limits: { cpu: 500m, memory: 512Mi }
```

Add `templates/artifacts.yaml` with Deployment + Service.

## Rollout Strategy

**Phase 1: Foundation (PR #1)**
- Database migration
- Basic artifacts service (create, view)
- Worker parses tags, creates artifacts
- UI renders artifact events in iframe

**Phase 2: Sharing (PR #2)**
- Public artifact URLs
- Share button in UI
- Permissions model

**Phase 3: Versioning UI (PR #3)**
- Version history view
- Rollback to previous version
- Diff view between versions

**Phase 4: Enhancements (future)**
- Direct editing in artifact UI
- Templates (docs, slides, designs)
- Dynamic content (API calls)
- Commenting
