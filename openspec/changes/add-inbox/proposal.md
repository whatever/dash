## Why

The agent can only reach the person through the reply they are watching. It has nowhere to put a question that needs an answer later, such as "may I run `git push`?", or a note worth keeping, such as "the build you asked about went green". With hermes, approvals also blocked a process for at most five minutes, then gave up. Once the agent runs inside the worker (`replace-hermes-with-agent-engine`), a tool call that needs a person can end the turn, wait on disk for as long as it takes, and continue when answered.

## What Changes

- An inbox of items, each either an **approval** (needs an answer) or a **message** (a note from the agent, nothing to do), with an API to list, count, answer and dismiss them.
- **Approvals:**
  - A tool set to `ask` in `AGENT_TOOL_POLICY` no longer runs straight away. The turn ends with an `approval` event, and an approval item records the call.
  - Answering every approval from a turn queues a `resume` job. That job runs the allowed calls, tells the model which were denied, and streams a new reply.
  - "Allow always" saves a rule for that tool with those exact arguments.
  - A new message in the conversation denies its open approvals. Approvals expire after 24 hours.
- **Messages:** a `leave_message` tool lets the agent add a message item with a title, a body and source links.
- The web UI gets an Inbox tab with an unread count, and an approval card in the chat.
- The chart's default policy sets `run_command` to `ask`. Nothing else is **BREAKING**: tools not set to `ask` behave as before.

## Capabilities

### New Capabilities

- `inbox`: inbox items, approvals and their answers, saved rules, expiry, and the agent's messages.

### Modified Capabilities

- `chat`: a reply can end waiting for approval, with an `approval` event, and the live timeline records `resume` jobs.

## Impact

- Code:
  - A migration for inbox items and tool rules, store methods, and inbox routes in `web.py`.
  - A `resume` job kind in `queue.py` and `worker.py`.
  - The approval wrapper and `leave_message` in `dash.agent`.
  - UI changes in `static/`, and tests.
- Operators: the chart sets `AGENT_TOOL_POLICY` to `{"run_command": "ask"}` by default. Deployments that want the old behaviour set it to `{}`.
- Cost: none. Waiting approvals are rows, not running processes.
- Depends on `replace-hermes-with-agent-engine`, which must be archived first, because both restate "Replies stream as job events".
