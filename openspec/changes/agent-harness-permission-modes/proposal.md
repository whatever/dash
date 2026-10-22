## Why

The in-process agent engine can now run tool calls, but every tool follows a single global policy: `never`, `ask`, or `auto`. The harness needs finer-grained control over the *flow* of approvals:

- **Manual mode**: no tool calls without explicit user approval. The agent can only give advice and reason. Useful for high-stakes decisions or exploring what the agent would do.
- **Auto mode**: tool calls run immediately with the global policy. This is today's behavior.
- **Fast-forward mode**: tool calls run through a safety classifier as the only gate (respecting `never` tools). The classifier uses heuristics, pattern matching, or a model to quickly allow or block commands without pausing for user input. Useful for trusted agents where the user wants speed over control.
- **Plan mode** (future): the agent plans the full sequence of tool calls, shows them to the user for review, and only runs them when approved as a unit. This keeps the conversation flowing with one decision point instead of many.

These modes change *when* tool calls are allowed, but not which ones. The `AGENT_TOOL_POLICY` map still says which tools the agent can see.

## What Changes

- Every chat job has a **permission mode**, set by the client when creating or updating the conversation, or taken from the user's default.
- **Manual mode** (`permission: manual`): tool calls are set to `ask` by policy and held for approval. An approved tool call is added as a `tool` event with `status` `approved` before it runs. Unapproved calls become an `error` event and end the turn.
- **Auto mode** (`permission: auto`): tool calls follow `AGENT_TOOL_POLICY` as now, and any `ask` tool is hidden from the agent.
- **Fast-forward mode** (`permission: fast-forward`): tool calls are sent through a safety classifier. The classifier checks the tool name and arguments against a configurable ruleset (heuristics, patterns, or a model). Calls that pass go straight to `running`; those that fail end the turn with an error. The `never` policy is still respected.
- **Plan mode** (placeholder for future): the agent receives a tool that emits a plan of calls, and the turn ends when the plan is ready.

## Capabilities

### New Capabilities

- `agent-harness-permission-modes`: the client chooses between manual approval, auto, fast-forward, and (future) plan modes for tool calls in a conversation.
- `agent-safety-classifier`: tool calls in fast-forward mode are gated by a pluggable safety classifier with configurable rules.

### Modified Capabilities

- `chat`: adding a `Conversation` field `permission_mode`, the `POST /api/conversations` body includes it, and the permission mode changes how tool events and job errors flow.

## Impact

- Code:
  - Added: an `Approval` table and its migration, a `permission_mode` field in `Conversation`, an approval queue, a safety classifier interface, and REST routes to approve/deny tool calls and configure the classifier.
  - Changed: `worker.py` to check permission mode and route tool calls to approval or classifier, `web.py` to add approval and classifier config routes, and `__init__.py` wiring.
- API:
  - `POST /api/conversations` and `PATCH /api/conversations/{id}` now accept `permission_mode`: `manual`, `auto`, `fast-forward`.
  - `POST /api/approvals/{job_id}/{toolCallId}` approves a tool call, and `DELETE` denies it.
  - `GET /api/safety-classifier/rules` lists configured rules, `POST` adds or updates them.
  - A tool call in manual mode generates a `tool` event with `status: awaiting_approval`, and in fast-forward mode is silent (allowed) or causes an `error` event (blocked).
- The `add-inbox` change will build on the approval queue.
- Open PRs: none directly affected. This is additive to the agent engine.
