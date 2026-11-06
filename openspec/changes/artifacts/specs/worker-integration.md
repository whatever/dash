# Worker Integration

## Overview

The worker parses Hermes responses for `<artifact>` tags, creates artifacts via the artifacts service internal API, and emits artifact events to Redis streams for the UI to consume.

## Artifact Tag Protocol

Hermes uses XML-like tags to signal artifact creation or updates:

### Create new artifact

```xml
<artifact type="markdown" title="OpenSpec: Artifacts System">
# Artifacts System

## Problem
Long content here...
</artifact>
```

### Update existing artifact

```xml
<artifact id="proposal-abc123" type="markdown" title="OpenSpec: Artifacts System">
# Artifacts System

## Problem
...

## Security Considerations
(new section added)
</artifact>
```

**Tag attributes:**
- `type` (required): 'html', 'markdown', 'react'
- `title` (required): Human-readable title
- `id` (optional): For updates, references existing artifact ID

## Worker Implementation

Add to `src/dash/worker.py`:

```python
import re
import httpx
from typing import Any

# Regex to extract artifact tags and attributes
ARTIFACT_TAG_RE = re.compile(
    r'<artifact\s+([^>]+)>(.+?)</artifact>',
    re.DOTALL | re.IGNORECASE
)
ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


def parse_artifact_tag(text: str) -> dict[str, Any] | None:
    """Extract artifact data from <artifact> tag in text."""
    match = ARTIFACT_TAG_RE.search(text)
    if not match:
        return None
    
    attrs_str, content = match.groups()
    attrs = dict(ATTR_RE.findall(attrs_str))
    
    if 'type' not in attrs or 'title' not in attrs:
        return None  # Missing required attributes
    
    return {
        'id': attrs.get('id'),  # None for new artifacts
        'type': attrs['type'],
        'title': attrs['title'],
        'content': content.strip(),
    }


class Worker:
    def __init__(
        self,
        *,
        store: Store,
        queue: Queue,
        chat: Chat,
        embedder: Embedder,
        extractor: Extractor,
        top_k: int,
        artifacts_url: str | None = None,  # NEW
    ) -> None:
        # ... existing fields ...
        self.artifacts_url = artifacts_url
        self.http = httpx.AsyncClient() if artifacts_url else None

    async def create_artifact(
        self,
        artifact_data: dict[str, Any],
        conversation_id: uuid.UUID,
        message_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Create or update an artifact via the artifacts service."""
        if not self.artifacts_url or not self.http:
            log.warning("Artifacts service not configured")
            return None
        
        try:
            if artifact_data.get('id'):
                # Update existing artifact
                response = await self.http.post(
                    f"{self.artifacts_url}/api/artifacts/{artifact_data['id']}/versions",
                    json={
                        'content': artifact_data['content'],
                        'message_id': message_id,
                    },
                    timeout=10.0,
                )
                response.raise_for_status()
                result = response.json()
                return {
                    'id': artifact_data['id'],
                    'version': result['version'],
                    'title': artifact_data['title'],
                    'type': artifact_data['type'],
                }
            else:
                # Create new artifact
                response = await self.http.post(
                    f"{self.artifacts_url}/api/artifacts",
                    json={
                        'type': artifact_data['type'],
                        'title': artifact_data['title'],
                        'content': artifact_data['content'],
                        'conversation_id': str(conversation_id),
                        'message_id': message_id,
                    },
                    timeout=10.0,
                )
                response.raise_for_status()
                result = response.json()
                return {
                    'id': result['id'],
                    'version': result['version'],
                    'title': artifact_data['title'],
                    'type': artifact_data['type'],
                    'url': result['url'],
                }
        except httpx.HTTPError as ex:
            log.exception("Failed to create artifact: %s", ex)
            return None

    async def handle_chat(self, job: Job) -> None:
        conversation_id = uuid.UUID(job.conversation_id)
        history = await self.store.messages(conversation_id)
        if not history or history[-1].role != "user":
            await self.queue.emit(job.job_id, "error", message="No user message to answer.")
            return
        
        user_text = history[-1].content
        trail: list[dict[str, Any]] = []

        async def emit(kind: str, **data: Any) -> None:
            await self.queue.emit(job.job_id, kind, **data)
            record(trail, kind, data)

        memories = await self.recall(user_text)
        if memories:
            await emit("memories", items=memories)

        conversation = conversation_key(conversation_id)
        instructions = system_prompt(memories)

        reply: list[str] = []
        buffers = {"text": "", "reasoning": ""}
        events = {"text": "delta", "reasoning": "reasoning"}
        
        # Accumulate full response to check for artifacts
        full_response = ""

        async def flush(kind: str) -> None:
            if buffers[kind]:
                await emit(events[kind], text=buffers[kind])
                buffers[kind] = ""

        try:
            async for delta in self.chat.stream(conversation, user_text, instructions):
                if delta.kind in buffers:
                    other = "reasoning" if delta.kind == "text" else "text"
                    await flush(other)
                    if delta.kind == "text":
                        reply.append(delta.text)
                        full_response += delta.text
                    buffers[delta.kind] += delta.text
                    if len(buffers[delta.kind]) >= FLUSH_CHARS:
                        await flush(delta.kind)
                else:
                    await flush("reasoning")
                    await flush("text")
                    await emit(delta.kind, **delta.data)
        except Exception as ex:
            log.exception("hermes call failed")
            await self.queue.emit(job.job_id, "error", message=f"hermes: {ex}")
            return
        
        await flush("reasoning")
        await flush("text")

        text = "".join(reply)
        message = await self.store.add_message(conversation_id, "assistant", text, trail)
        
        # Check for artifact tag in response
        artifact_data = parse_artifact_tag(full_response)
        if artifact_data:
            artifact = await self.create_artifact(
                artifact_data,
                conversation_id,
                message.id
            )
            if artifact:
                await emit("artifact",
                    id=artifact['id'],
                    title=artifact['title'],
                    type=artifact['type'],
                    version=artifact['version'],
                    url=artifact.get('url', f"/artifacts/{artifact['id']}/preview")
                )

        await self.queue.emit(job.job_id, "done", message_id=message.id)
        
        stored = await self.remember(user_text, text)
        if stored:
            log.info("stored %d new memories", stored)

    async def close(self) -> None:
        """Clean up HTTP client."""
        if self.http:
            await self.http.aclose()
```

## Configuration

Add to `src/dash/config.py`:

```python
@dataclass(frozen=True)
class Settings:
    # ... existing fields ...
    artifacts_url: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            # ... existing fields ...
            artifacts_url=_env("ARTIFACTS_URL", "http://dash-artifacts:8000").rstrip("/"),
        )
```

Add to Helm chart env vars:

```yaml
# templates/worker.yaml
env:
  # ... existing vars ...
  - name: ARTIFACTS_URL
    value: "http://dash-artifacts:8000"
```

## Message Event Schema

Artifact events are added to the `messages.events` JSONB array:

```json
{
  "kind": "artifact",
  "id": "proposal-abc123",
  "title": "OpenSpec: Artifacts System",
  "type": "markdown",
  "version": 1,
  "url": "/artifacts/proposal-abc123/preview"
}
```

## Agent Instructions

Add to Hermes system prompt to teach artifact syntax:

```markdown
## Artifacts

For substantial, self-contained content (proposals, designs, documentation), create an artifact using:

<artifact type="markdown" title="Descriptive Title">
Content here...
</artifact>

Supported types: markdown, html, react

To update an existing artifact, include the id attribute:

<artifact id="proposal-abc123" type="markdown" title="Updated Title">
Updated content...
</artifact>

Use artifacts for:
- OpenSpec proposals
- Design documents
- Project documentation
- Data visualizations
- Code examples with explanation

Do NOT use artifacts for:
- Brief answers (< 20 lines)
- Content that needs conversation context
- Interactive discussions
```

## Testing

```python
# tests/test_worker_artifacts.py

def test_parse_artifact_tag():
    text = '''<artifact type="markdown" title="Test">
# Content
</artifact>'''
    result = parse_artifact_tag(text)
    assert result == {
        'id': None,
        'type': 'markdown',
        'title': 'Test',
        'content': '# Content'
    }

def test_parse_artifact_update():
    text = '<artifact id="abc123" type="html" title="Test">Content</artifact>'
    result = parse_artifact_tag(text)
    assert result['id'] == 'abc123'

async def test_create_artifact(worker, httpx_mock):
    httpx_mock.add_response(
        url="http://artifacts:8000/api/artifacts",
        json={"id": "art-123", "version": 1, "url": "/artifacts/art-123/preview"}
    )
    
    artifact = await worker.create_artifact(
        {'type': 'markdown', 'title': 'Test', 'content': '# Test'},
        conversation_id=uuid.uuid4(),
        message_id=42
    )
    assert artifact['id'] == 'art-123'
    assert artifact['version'] == 1
```

## Error Handling

If artifacts service is unavailable:
- Log warning
- Continue processing chat normally
- Don't emit artifact event
- User sees response in chat (without artifact panel)

If artifact creation fails:
- Log error
- Emit error event to UI (optional)
- Response still appears in chat

This ensures degraded but functional behavior if artifacts service is down.
