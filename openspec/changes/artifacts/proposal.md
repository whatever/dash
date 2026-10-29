# Artifacts System

## Problem

Currently, dash displays all content inline in the chat conversation. This works for quick answers but falls short for substantial, self-contained content like:

1. **OpenSpec proposals** - Multi-section documents that users want to share with teammates
2. **Design mockups** - HTML/CSS prototypes that need live preview
3. **Data visualizations** - Charts and dashboards built from project data
4. **Documentation** - Project wikis, API specs, architecture diagrams

Users need to:
- Create substantial content without it cluttering the chat
- Share it with teammates (e.g., "send this proposal to Matt")
- Iterate on it through conversation ("update the security section")
- View version history to see what changed
- Access it later without scrolling through chat history

## Solution

Implement an **Artifacts system** - a dedicated panel for substantial, self-contained content that can be created, viewed, edited, and shared independently of the chat conversation.

### Core Capabilities

1. **Creation** - Agent generates content with `<artifact>` tags, worker creates artifact, UI renders in iframe
2. **Viewing** - Artifacts appear in dedicated panel beside chat, with live preview for HTML/markdown
3. **Editing** - Update via chat ("add a security section") or (future) direct editing in UI
4. **Versioning** - Every edit creates a new version, tied to the chat message that created it
5. **Sharing** - Generate shareable URLs with org-based or explicit permissions
6. **Persistence** - Artifacts stored in database, accessible from any conversation

### Architecture

**Artifacts Service** - New FastAPI service deployed as separate pod:
- Shares Postgres database with dash
- Internal API for worker (create/update artifacts)
- Public API for browser (view, list, share)
- Renders artifacts at `/artifacts/{id}/preview`

**Database** - Two new tables:
- `artifacts` - Metadata (id, title, type, conversation_id, visibility)
- `artifact_versions` - Content history (version, content, message_id, created_at)

**Worker Integration** - Parse Hermes responses for `<artifact>` tags, create artifacts via internal API, emit events

**UI Rendering** - Detect artifact events in SSE stream, render iframe in chat panel

## User Flow

### Basic Creation & Sharing
```
User: "Create an OpenSpec proposal for dash artifacts"
  ↓
Hermes generates markdown proposal
  ↓
Worker detects <artifact type="markdown" title="...">content</artifact>
  ↓
POSTs to artifacts service → returns ID
  ↓
Emits event: {"kind": "artifact", "id": "proposal-abc123"}
  ↓
UI shows iframe rendering the artifact
  ↓
User clicks "Share" → gets URL: artifacts.dash.com/proposal-abc123
  ↓
Sends to Matt → both can view through browsers
```

### Iterating
```
User: "Update the artifact - add a security considerations section"
  ↓
Hermes knows current artifact ID from context
  ↓
Fetches current content via internal API
  ↓
Generates updated markdown with new section
  ↓
POSTs new version → artifact_versions.version=2
  ↓
Emits artifact event with version=2
  ↓
UI iframe auto-refreshes to show new version
```

## Key Benefits

- **Focused conversation** - Long content doesn't clutter chat
- **Easy sharing** - Generate links teammates can open
- **Version history** - See how content evolved, tied to conversation
- **Live preview** - HTML/markdown renders immediately
- **Reusable** - Access artifacts from any conversation
- **Scalable** - Separate service, scales independently

## Scope

This feature includes:
- Database schema (artifacts, artifact_versions tables)
- Artifacts service (FastAPI app, Helm deployment)
- Worker integration (parse tags, create artifacts, emit events)
- UI rendering (iframe, share button, version display)
- Permissions (org-based visibility for V1)

Out of scope (future enhancements):
- Direct editing in artifact UI (V1 is chat-only editing)
- Real-time collaboration
- Commenting within artifacts
- Dynamic content (client/server-side APIs)
- Templates (like Claude's Docs/Slides/Design)

## Migration Path

No breaking changes. This is purely additive:
1. Database migration adds new tables
2. Artifacts service deploys as new pod
3. Worker learns to parse artifact tags
4. UI learns to render artifact events
5. Existing conversations unaffected

## Success Metrics

- Users create artifacts for substantial content (proposals, designs, docs)
- Artifacts are shared with teammates
- Users iterate on artifacts through conversation
- Reduced clutter in chat (long content moves to artifacts)
