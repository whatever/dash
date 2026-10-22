## 1. Data Model

- [ ] 1.1 Add a migration for `permission_mode` field on `Conversation` (default `auto`). Verify: the offline migration test renders the table with the new field.
- [ ] 1.2 Add an `Approval` table (job_id, tool_call_id, tool_name, arguments, status, created_at, decided_at). Verify: migrations apply cleanly, and the table exists in the test database.

## 2. API Changes

- [ ] 2.1 Add `permission_mode` to the `POST /api/conversations` body (optional, defaults to `auto`). Verify: creating a conversation with `permission_mode: manual` sets it on the row.
- [ ] 2.2 Add `PATCH /api/conversations/{id}` to update `permission_mode` (and other fields later). Verify: the mode changes on the conversation, and existing jobs are not affected.
- [ ] 2.3 Add `POST /api/approvals/{job_id}/{toolCallId}` to approve a tool call and `DELETE` to deny it. Verify: approval is recorded and the worker wakes up.

## 3. Worker Logic

- [ ] 3.1 Pass `permission_mode` to the agent engine and the tool handlers. Verify: the mode is available in the tool context.
- [ ] 3.2 When a tool call arrives in manual mode, emit a `tool` event with `status: awaiting_approval` and enqueue it. Verify: the event stream shows `awaiting_approval` before `approved` or `denied`.
- [ ] 3.3 Poll the approval queue with the timeout. When approved, emit `approved` and run the tool. When denied or timeout, end the turn with an `error` event. Verify: tests for approve, deny, and timeout paths.
- [ ] 3.4 In auto mode, tools follow `AGENT_TOOL_POLICY` as now and are not queued. Verify: no `awaiting_approval` events appear in auto mode.

## 4. Event Semantics

- [ ] 4.1 Define tool event statuses: `awaiting_approval`, `approved`, `running`, `completed`, `failed`, `interrupted`, and `denied`. Verify: the event contract tests cover the new statuses.
- [ ] 4.2 A denied tool call ends the turn with an `error` event. Verify: a turned-down tool causes the job to end with an error, not continue.

## 5. Testing

- [ ] 5.1 Unit tests for approval queueing and timeout. Verify: a tool in manual mode queues, approval unblocks it, denial ends the turn, and timeout ends the turn.
- [ ] 5.2 API tests for approval endpoints. Verify: `POST` and `DELETE` record decisions and return 200, or 404 if the job or approval does not exist.
- [ ] 5.3 Integration tests for manual, auto, and plan modes. Verify: a multi-turn conversation in each mode shows the expected events and approvals.

## 6. Plan Mode Stub

- [ ] 6.1 Accept `permission_mode: plan` on conversation creation and PATCH. Verify: the database stores `plan`, and the API accepts it.
- [ ] 6.2 Behavior is a placeholder: `plan` mode acts like `manual` for now. Verify: a conversation in plan mode queues approvals as if it were manual.

## 7. Checks

- [ ] 7.1 Run the repo checks. Verify: `uv run ruff check`, `uv run ruff format --check`, `uv run pyright` and `uv run pytest` pass.
- [ ] 7.2 Validate the change. Verify: `openspec validate agent-harness-permission-modes --strict` passes.
