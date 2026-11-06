# Artifacts System - Implementation Tasks

## Phase 1: Foundation

### Database Schema
- [ ] Create Alembic migration for `artifacts` table
- [ ] Create Alembic migration for `artifact_versions` table
- [ ] Add SQLAlchemy models to `src/dash/db.py`
- [ ] Add Store methods: `create_artifact()`, `add_artifact_version()`, `get_artifact()`, `list_artifacts()`
- [ ] Test migrations locally and in CI

### Artifacts Service
- [ ] Create `src/dash/artifacts.py` with FastAPI app
- [ ] Implement `POST /api/artifacts` (internal)
- [ ] Implement `POST /api/artifacts/{id}/versions` (internal)
- [ ] Implement `GET /artifacts/{id}/preview` (public, with auth)
- [ ] Implement `GET /api/artifacts` (list)
- [ ] Implement `GET /api/artifacts/{id}/raw` (get source)
- [ ] Add markdown → HTML rendering
- [ ] Add HTML sanitization/CSP headers
- [ ] Add nanoid generation for artifact IDs
- [ ] Write unit tests for service

### Worker Integration
- [ ] Add artifact tag parser to `src/dash/worker.py`
- [ ] Integrate artifact creation in `handle_chat()`
- [ ] Add httpx client for internal artifacts API calls
- [ ] Emit artifact events to Redis stream
- [ ] Handle artifact updates (when `id` attr present)
- [ ] Add error handling for artifact service failures
- [ ] Write tests for artifact tag parsing

### UI Rendering
- [ ] Update `src/dash/static/app.js` to detect artifact events
- [ ] Render iframe for artifact preview
- [ ] Add loading state while artifact renders
- [ ] Add error handling for failed artifact loads
- [ ] Style artifact panel to match chat UI
- [ ] Test artifact rendering in different browsers

### Helm Chart
- [ ] Create `charts/dash/templates/artifacts.yaml`
- [ ] Add artifacts Deployment with proper resource limits
- [ ] Add artifacts Service
- [ ] Add artifacts configuration to `values.yaml`
- [ ] Update `values-local.yaml` for local testing
- [ ] Test deployment on Rancher Desktop

## Phase 2: Sharing & Permissions

### Sharing
- [ ] Add "Share" button to artifact UI
- [ ] Implement shareable URL generation
- [ ] Add org-based permission checking
- [ ] Add public/private visibility toggle
- [ ] Test sharing flow end-to-end

### Permissions
- [ ] Implement permission check middleware
- [ ] Add `PATCH /api/artifacts/{id}` for visibility updates
- [ ] Add UI for changing visibility
- [ ] Test permission scenarios (org member, non-member, public)

## Phase 3: Version History

### Backend
- [ ] Add `GET /api/artifacts/{id}/versions` endpoint
- [ ] Add version rollback endpoint
- [ ] Store version diffs (optional optimization)

### UI
- [ ] Add version history panel
- [ ] Add "View history" button
- [ ] Add version selector dropdown
- [ ] Add rollback confirmation dialog
- [ ] Show which chat message created each version

## Documentation

- [ ] Add artifacts section to README.md
- [ ] Document artifact tag syntax for Hermes
- [ ] Add architecture diagram
- [ ] Write API documentation
- [ ] Add example artifacts to demo

## Testing

- [ ] Unit tests for Store methods
- [ ] Unit tests for artifacts service endpoints
- [ ] Integration tests for worker→artifacts flow
- [ ] E2E tests for create→view→share flow
- [ ] Load testing for concurrent artifact creation
- [ ] Security testing (XSS, injection)

## Deployment

- [ ] Test migration on staging database
- [ ] Deploy artifacts service to staging
- [ ] Verify artifacts work on staging
- [ ] Deploy to production
- [ ] Monitor metrics (artifact creation rate, render time)
- [ ] Set up alerts for service health

## Future Enhancements (not blocking)

- [ ] Direct editing in artifact UI
- [ ] Real-time collaboration (WebSockets)
- [ ] Commenting system within artifacts
- [ ] Templates (docs, slides, designs)
- [ ] Dynamic content (API calls from artifacts)
- [ ] Export to PDF/Word/etc
- [ ] Full-text search within artifacts
- [ ] Artifact analytics (views, shares)
