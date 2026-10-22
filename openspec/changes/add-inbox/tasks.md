## 1. Data

- [ ] 1.1 Add a migration for `inbox_items` and `tool_rules`. Verify: the offline migration test renders both tables, and there is a single head.
- [ ] 1.2 Add store methods to open, list, count, resolve, dismiss and expire items, and to save, match, list and delete rules. Verify: unit tests against the fake store, plus the SQL shape tests the repo already uses.

## 2. Approvals

- [ ] 2.1 Wrap `ask` tools in the approval check, which skips asking when a rule matches exactly. Verify: `FunctionModel` tests that an `ask` call does not run, a matching rule runs it, and different arguments still ask.
- [ ] 2.2 End a turn that has waiting calls: store the reply so far, open one item per call, and emit `approval` events and `done` with `awaiting`. Verify: worker tests assert the exact events, the items and the stored `Conversation`.
- [ ] 2.3 Add the `resume` job kind. Queue it when a turn's last open approval is answered, and run it with `ToolApproved` or `ToolDenied` for each call. Verify: tests for allow, deny, `allow_always` saving a rule, and two approvals from one turn.
- [ ] 2.4 Deny open approvals as `superseded` when a new message arrives, in the same run as the new prompt. Verify: a test that the model request carries both the denial and the new message.
- [ ] 2.5 Expire approvals older than 24 hours in the worker loop, and report them as denied on the next turn. Verify: a test with a frozen clock.

## 3. Messages

- [ ] 3.1 Add `leave_message`, with its length and source limits. Verify: tests for a valid note, an oversized body, and policy `never` hiding it.

## 4. API and UI

- [ ] 4.1 Add `GET /api/inbox`, `GET /api/inbox/count`, `POST /api/inbox/{id}/resolve`, `POST /api/inbox/{id}/dismiss`, `GET /api/inbox/rules` and `DELETE /api/inbox/rules/{id}`. Verify: API tests for every scenario in the `inbox` spec, including 404 and 409.
- [ ] 4.2 Add an Inbox tab with an unread badge, an approval card in the chat (allow, always, deny), and messages that link back to their conversation. Verify: on the compose stack, an `ask` call shows the card, allowing it resumes the reply, and the badge count follows the inbox.
- [ ] 4.2a Make resolve idempotent, add `GET /api/inbox/{id}`, key rules on the tool name, put `conversation_id` in the `approval` event, and have the chat card read its item's state and act on its own conversation. Verify: tests for the double resolve, concurrent resolves, a rule that holds in another conversation, the event's `conversation_id`; on the compose stack, answering in the inbox updates the open chat.
- [ ] 4.3 Set the chart's default `AGENT_TOOL_POLICY` to `{"run_command": "ask"}`, and document how to turn it off. Verify: `helm template` shows the value, and the README explains it.

## 5. Checks

- [ ] 5.1 Run the repo checks. Verify: `uv run ruff check`, `uv run ruff format --check`, `uv run pyright` and `uv run pytest` pass.
- [ ] 5.2 Validate the change. Verify: `openspec validate add-inbox --strict` passes.
- [ ] 5.3 Archive `replace-hermes-with-agent-engine` before this change, then write the `## Purpose` of the new `agent-tools` and `inbox` specs and update the `chat` Purpose, which still names hermes. Verify: `openspec archive` applies both in order, and `openspec validate --all --strict` passes afterwards.
