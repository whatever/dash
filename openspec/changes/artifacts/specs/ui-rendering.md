# UI Rendering

## Overview

The dash UI detects artifact events in the SSE stream and renders artifacts in an iframe panel beside the chat. Users can view, share, and (future) edit artifacts directly in the UI.

## Event Detection

Add to `src/dash/static/app.js`:

```javascript
// Existing event handler
function handleEvent(event) {
  if (event.kind === 'delta') {
    appendDelta(event.text);
  } else if (event.kind === 'memories') {
    showMemories(event.items);
  } else if (event.kind === 'artifact') {
    // NEW: Render artifact
    renderArtifact(event);
  }
  // ... other event types ...
}

function renderArtifact(event) {
  // Create artifact panel if it doesn't exist
  let panel = document.getElementById('artifact-panel');
  if (!panel) {
    panel = createArtifactPanel();
    document.body.appendChild(panel);
  }
  
  // Update panel content
  const iframe = panel.querySelector('iframe');
  iframe.src = event.url;
  
  // Update metadata
  panel.querySelector('.artifact-title').textContent = event.title;
  panel.querySelector('.artifact-version').textContent = `v${event.version}`;
  panel.dataset.artifactId = event.id;
  
  // Show panel
  panel.classList.remove('hidden');
  
  // Add artifact indicator to chat message
  const indicator = document.createElement('div');
  indicator.className = 'artifact-indicator';
  indicator.innerHTML = `
    <span class="icon">📄</span>
    <span class="title">${event.title}</span>
    <button onclick="showArtifact('${event.id}')">View</button>
  `;
  document.querySelector('.messages').appendChild(indicator);
}

function createArtifactPanel() {
  const panel = document.createElement('div');
  panel.id = 'artifact-panel';
  panel.className = 'artifact-panel hidden';
  panel.innerHTML = `
    <div class="artifact-header">
      <div class="artifact-info">
        <h3 class="artifact-title"></h3>
        <span class="artifact-version"></span>
      </div>
      <div class="artifact-actions">
        <button onclick="shareArtifact()">Share</button>
        <button onclick="closeArtifact()">✕</button>
      </div>
    </div>
    <div class="artifact-body">
      <iframe sandbox="allow-same-origin" loading="lazy"></iframe>
    </div>
  `;
  return panel;
}

function showArtifact(artifactId) {
  const panel = document.getElementById('artifact-panel');
  if (!panel) return;
  
  const iframe = panel.querySelector('iframe');
  iframe.src = `/artifacts/${artifactId}/preview`;
  panel.dataset.artifactId = artifactId;
  panel.classList.remove('hidden');
}

function closeArtifact() {
  const panel = document.getElementById('artifact-panel');
  if (panel) {
    panel.classList.add('hidden');
  }
}

async function shareArtifact() {
  const panel = document.getElementById('artifact-panel');
  if (!panel) return;
  
  const artifactId = panel.dataset.artifactId;
  const url = `${window.location.origin}/artifacts/${artifactId}/preview`;
  
  try {
    await navigator.clipboard.writeText(url);
    showNotification('Link copied to clipboard!');
  } catch (err) {
    // Fallback: show link in modal
    prompt('Copy this link:', url);
  }
}

function showNotification(message) {
  const notification = document.createElement('div');
  notification.className = 'notification';
  notification.textContent = message;
  document.body.appendChild(notification);
  setTimeout(() => notification.remove(), 3000);
}
```

## Styling

Add to `src/dash/static/style.css`:

```css
/* Artifact Panel */
.artifact-panel {
  position: fixed;
  right: 0;
  top: 0;
  bottom: 0;
  width: 50%;
  background: white;
  border-left: 1px solid #ddd;
  display: flex;
  flex-direction: column;
  z-index: 1000;
  box-shadow: -2px 0 8px rgba(0,0,0,0.1);
}

.artifact-panel.hidden {
  display: none;
}

.artifact-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-bottom: 1px solid #ddd;
  background: #f9f9f9;
}

.artifact-info {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
}

.artifact-title {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
}

.artifact-version {
  color: #666;
  font-size: 0.85rem;
}

.artifact-actions {
  display: flex;
  gap: 0.5rem;
}

.artifact-actions button {
  padding: 0.4rem 0.8rem;
  border: 1px solid #ddd;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9rem;
}

.artifact-actions button:hover {
  background: #f5f5f5;
}

.artifact-body {
  flex: 1;
  overflow: hidden;
}

.artifact-body iframe {
  width: 100%;
  height: 100%;
  border: none;
}

/* Artifact Indicator in Chat */
.artifact-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  margin: 0.5rem 0;
  background: #f0f7ff;
  border: 1px solid #b3d9ff;
  border-radius: 4px;
}

.artifact-indicator .icon {
  font-size: 1.2rem;
}

.artifact-indicator .title {
  flex: 1;
  font-weight: 500;
}

.artifact-indicator button {
  padding: 0.3rem 0.6rem;
  background: white;
  border: 1px solid #0066cc;
  color: #0066cc;
  border-radius: 3px;
  cursor: pointer;
  font-size: 0.9rem;
}

.artifact-indicator button:hover {
  background: #0066cc;
  color: white;
}

/* Notification Toast */
.notification {
  position: fixed;
  bottom: 2rem;
  right: 2rem;
  padding: 1rem 1.5rem;
  background: #333;
  color: white;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.2);
  animation: slideIn 0.3s ease-out;
}

@keyframes slideIn {
  from {
    transform: translateY(100%);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}

/* Responsive: Stack on small screens */
@media (max-width: 768px) {
  .artifact-panel {
    width: 100%;
  }
}
```

## HTML Updates

Update `src/dash/static/index.html` to prepare for artifacts:

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>dash</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <div class="container">
    <aside class="sidebar">
      <!-- existing sidebar content -->
    </aside>
    
    <main class="main">
      <div class="messages"></div>
      <form class="input-form">
        <textarea></textarea>
        <button type="submit">Send</button>
      </form>
    </main>
  </div>
  
  <!-- Artifact panel is created dynamically -->
  
  <script src="/static/lib.js"></script>
  <script src="/static/app.js"></script>
</body>
</html>
```

## Message Persistence

When page reloads, artifacts should be restored:

```javascript
async function loadMessages(conversationId) {
  const response = await fetch(`/api/conversations/${conversationId}/messages`);
  const messages = await response.json();
  
  for (const msg of messages) {
    appendMessage(msg.role, msg.content);
    
    // Replay events (including artifacts)
    for (const event of msg.events || []) {
      if (event.kind === 'artifact') {
        renderArtifact(event);
      }
      // ... other events ...
    }
  }
}
```

## Direct Artifact Access

Allow opening artifacts directly via URL: `/artifacts/{id}/preview`

This is handled by the artifacts service, not the dash UI. The UI only needs to handle artifacts embedded in conversations.

## Future: Artifact Library View

Add a new view to list all artifacts:

```javascript
// Add to navigation
async function showArtifactsLibrary() {
  const response = await fetch('/api/artifacts');
  const artifacts = await response.json();
  
  const list = artifacts.map(a => `
    <div class="artifact-card" onclick="showArtifact('${a.id}')">
      <h4>${a.title}</h4>
      <div class="metadata">
        <span>${a.type}</span>
        <span>v${a.version}</span>
        <span>${formatDate(a.updated_at)}</span>
      </div>
    </div>
  `).join('');
  
  document.querySelector('.main').innerHTML = `
    <div class="artifacts-library">
      <h2>Artifacts</h2>
      <div class="artifacts-grid">${list}</div>
    </div>
  `;
}
```

## Testing

Manual testing checklist:

- [ ] Create artifact via chat, verify panel appears
- [ ] Click "View" button, verify artifact loads
- [ ] Click "Share" button, verify URL copied
- [ ] Close artifact panel, verify it hides
- [ ] Reload page, verify artifact indicators restored
- [ ] Open artifact directly via URL
- [ ] Test on mobile (panel should be full-screen)
- [ ] Test with long artifact content (scrolling)
- [ ] Test with markdown rendering
- [ ] Test with multiple artifacts in one conversation

## Security Considerations

**iframe sandbox:**
- Use `sandbox="allow-same-origin"` attribute
- Prevents JavaScript execution in V1 (static content only)
- Future: Add `allow-scripts` when dynamic content is supported

**CSP headers:**
- Artifacts service sets `Content-Security-Policy`
- Prevents XSS attacks
- Restricts external resource loading

**Authentication:**
- Artifacts service checks org membership before serving
- Same auth as dash API (session cookies)
