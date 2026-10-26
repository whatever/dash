# Artifacts Service

## Overview

The artifacts service is a new FastAPI application deployed as a separate pod. It handles artifact creation, versioning, rendering, and serving. It shares the Postgres database with dash.

## Service Architecture

```
artifacts.py (FastAPI app)
  ├─ Internal API (called by worker)
  │   ├─ POST /api/artifacts
  │   └─ POST /api/artifacts/{id}/versions
  │
  ├─ Public API (called by browser)
  │   ├─ GET /artifacts/{id}/preview
  │   ├─ GET /api/artifacts
  │   ├─ GET /api/artifacts/{id}/raw
  │   └─ PATCH /api/artifacts/{id}
  │
  └─ Rendering
      ├─ Markdown → HTML
      ├─ HTML sanitization
      └─ CSP headers
```

## Implementation

Create `src/dash/artifacts.py`:

```python
import secrets
from pathlib import Path
from typing import Any

import markdown
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from dash.db import Store

# Simple nanoid alternative: URL-safe random string
def generate_id(prefix: str = "artifact") -> str:
    random_part = secrets.token_urlsafe(12)  # 16 chars
    return f"{prefix}-{random_part}"


class CreateArtifactRequest(BaseModel):
    type: str = Field(pattern="^(html|markdown|react)$")
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=1_000_000)
    conversation_id: str | None = None
    message_id: int | None = None


class AddVersionRequest(BaseModel):
    content: str = Field(min_length=1, max_length=1_000_000)
    message_id: int | None = None


def render_markdown(content: str) -> str:
    """Convert markdown to HTML with safe extensions."""
    html = markdown.markdown(
        content,
        extensions=['fenced_code', 'tables', 'nl2br'],
        output_format='html5'
    )
    return html


def wrap_html(title: str, content: str, artifact_type: str) -> str:
    """Wrap content in full HTML document with styling."""
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
            color: #333;
        }}
        h1, h2, h3 {{ color: #111; }}
        code {{
            background: #f4f4f4;
            padding: 0.2em 0.4em;
            border-radius: 3px;
            font-size: 0.9em;
        }}
        pre {{
            background: #f4f4f4;
            padding: 1rem;
            border-radius: 5px;
            overflow-x: auto;
        }}
        pre code {{
            background: none;
            padding: 0;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 1rem 0;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 0.5rem;
            text-align: left;
        }}
        th {{ background: #f4f4f4; }}
    </style>
</head>
<body>
{content}
</body>
</html>
"""


def create_app(store: Store) -> FastAPI:
    app = FastAPI(title="dash-artifacts", docs_url=None, redoc_url=None)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # Internal API (called by worker)
    
    @app.post("/api/artifacts", status_code=201)
    async def create_artifact(body: CreateArtifactRequest) -> dict[str, Any]:
        artifact_id = generate_id("artifact")
        conversation_id = uuid.UUID(body.conversation_id) if body.conversation_id else None
        
        artifact = await store.create_artifact(
            artifact_id=artifact_id,
            title=body.title,
            type=body.type,
            content=body.content,
            conversation_id=conversation_id,
            message_id=body.message_id,
        )
        return {
            "id": artifact.id,
            "version": artifact.current_version,
            "url": f"/artifacts/{artifact.id}/preview",
        }

    @app.post("/api/artifacts/{artifact_id}/versions")
    async def add_version(artifact_id: str, body: AddVersionRequest) -> dict[str, int]:
        try:
            version = await store.add_artifact_version(
                artifact_id=artifact_id,
                content=body.content,
                message_id=body.message_id,
            )
            return {"version": version}
        except ValueError as ex:
            raise HTTPException(404, str(ex))

    # Public API (called by browser)
    
    @app.get("/artifacts/{artifact_id}/preview")
    async def preview(artifact_id: str, version: int | None = None) -> HTMLResponse:
        result = await store.get_artifact(artifact_id, version)
        if result is None:
            raise HTTPException(404, "Artifact not found")
        
        artifact, artifact_version = result
        
        # TODO: Add permission check here (org-based for V1)
        
        if artifact.type == "markdown":
            html_content = render_markdown(artifact_version.content)
            html = wrap_html(artifact.title, html_content, artifact.type)
        elif artifact.type == "html":
            # Serve user HTML directly (TODO: add sanitization)
            html = artifact_version.content
        else:
            raise HTTPException(400, f"Unsupported type: {artifact.type}")
        
        return HTMLResponse(
            content=html,
            headers={
                "Content-Security-Policy": "default-src 'self' 'unsafe-inline'; script-src 'none';",
                "X-Frame-Options": "SAMEORIGIN",
            }
        )

    @app.get("/api/artifacts")
    async def list_artifacts(conversation_id: str | None = None) -> list[dict[str, Any]]:
        conv_id = uuid.UUID(conversation_id) if conversation_id else None
        artifacts = await store.list_artifacts(conv_id)
        return [
            {
                "id": a.id,
                "title": a.title,
                "type": a.type,
                "version": a.current_version,
                "created_at": a.created_at.isoformat(),
                "updated_at": a.updated_at.isoformat(),
            }
            for a in artifacts
        ]

    @app.get("/api/artifacts/{artifact_id}/raw")
    async def get_raw(artifact_id: str, version: int | None = None) -> dict[str, Any]:
        result = await store.get_artifact(artifact_id, version)
        if result is None:
            raise HTTPException(404, "Artifact not found")
        
        artifact, artifact_version = result
        
        # TODO: Add permission check
        
        return {
            "id": artifact.id,
            "title": artifact.title,
            "type": artifact.type,
            "version": artifact_version.version,
            "content": artifact_version.content,
            "created_at": artifact_version.created_at.isoformat(),
        }

    @app.patch("/api/artifacts/{artifact_id}")
    async def update_metadata(artifact_id: str, visibility: str | None = None) -> dict[str, str]:
        # TODO: Implement metadata updates (visibility, title, etc.)
        raise HTTPException(501, "Not implemented yet")

    return app


def create_production_app() -> FastAPI:
    """Factory for uvicorn: wires real Postgres from environment."""
    from dash.config import Settings
    
    settings = Settings.from_env()
    store = Store.from_url(settings.database_url)
    return create_app(store)
```

## Deployment

Add to `charts/dash/values.yaml`:

```yaml
artifacts:
  enabled: true
  replicas: 2
  image: ""  # defaults to dash.image
  resources:
    requests: { cpu: 100m, memory: 256Mi }
    limits: { cpu: 500m, memory: 512Mi }
```

Create `charts/dash/templates/artifacts.yaml`:

```yaml
{{- if .Values.artifacts.enabled }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dash-artifacts
  labels:
    {{- include "dash.labels" . | nindent 4 }}
    app.kubernetes.io/component: artifacts
spec:
  replicas: {{ .Values.artifacts.replicas }}
  selector:
    matchLabels:
      {{- include "dash.selectorLabels" . | nindent 6 }}
      app.kubernetes.io/component: artifacts
  template:
    metadata:
      labels:
        {{- include "dash.selectorLabels" . | nindent 8 }}
        app.kubernetes.io/component: artifacts
    spec:
      containers:
      - name: artifacts
        image: {{ .Values.artifacts.image | default .Values.dash.image }}
        imagePullPolicy: {{ .Values.dash.imagePullPolicy }}
        command: ["uvicorn", "dash.artifacts:create_production_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
        ports:
        - name: http
          containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: {{ .Values.postgres.existingSecret }}
              key: DASH_DATABASE_URL
        resources:
          {{- toYaml .Values.artifacts.resources | nindent 10 }}
        livenessProbe:
          httpGet:
            path: /healthz
            port: http
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /healthz
            port: http
          initialDelaySeconds: 5
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: dash-artifacts
  labels:
    {{- include "dash.labels" . | nindent 4 }}
    app.kubernetes.io/component: artifacts
spec:
  type: ClusterIP
  ports:
  - port: 8000
    targetPort: http
    protocol: TCP
    name: http
  selector:
    {{- include "dash.selectorLabels" . | nindent 4 }}
    app.kubernetes.io/component: artifacts
{{- end }}
```

## Testing

```python
# tests/test_artifacts_service.py
from fastapi.testclient import TestClient

def test_create_artifact(client: TestClient):
    response = client.post("/api/artifacts", json={
        "type": "markdown",
        "title": "Test Proposal",
        "content": "# Test\n\nContent"
    })
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["version"] == 1

def test_preview_markdown(client: TestClient, artifact_id: str):
    response = client.get(f"/artifacts/{artifact_id}/preview")
    assert response.status_code == 200
    assert "<h1>Test</h1>" in response.text
    assert "Content-Security-Policy" in response.headers
```

## Local Development

```sh
# Terminal 1: Run artifacts service
export DATABASE_URL=postgresql://postgres:dash@localhost:5432/postgres
uvicorn dash.artifacts:create_production_app --factory --reload --port 8001

# Terminal 2: Test endpoints
curl http://localhost:8001/healthz
curl -X POST http://localhost:8001/api/artifacts \
  -H "Content-Type: application/json" \
  -d '{"type":"markdown","title":"Test","content":"# Hello"}'
```
