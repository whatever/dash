## Context

**Agent harness today.** A chat job runs the agent on a single global tool policy: `never`, `ask`, or `auto`. In `ask` mode, all tools are hidden from the agent, so nothing runs unasked. The `add-inbox` change will queue `ask` tool calls for approval from a person. But the harness needs different modes:

- **Manual mode**: for exploring what the agent would do or for high-stakes conversations, where every tool call waits for explicit approval.
- **Auto mode**: the current behavior, where tool calls follow the global policy.
- **Plan mode** (future): the agent builds a full plan of tool calls, the user approves the plan, and then it runs as one unit.

These modes change the *flow* of approvals, not which tools are available.

## Goals / Non-Goals

**Goals**
- Manual mode lets the user approve each tool call individually before it runs.
- Auto mode keeps today's behavior unchanged.
- Plan mode is a placeholder for a later change.
- A user can set a default permission mode for their conversations.
- The event stream shows the new statuses: `awaiting_approval`, `approved` and `denied`.

**Non-Goals**
- Changing which tools the agent can see (that is `AGENT_TOOL_POLICY`).
- Per-tool modes or per-conversation rules beyond approval flow.
- A UI for setting approvals beyond the API.
- Integrating with the inbox beyond passing the approval queue.

## Decisions

**Store the permission mode on the conversation.** Each conversation has one mode, set when creating it or later with a PATCH. This lets a user start in manual mode and switch to auto once they trust the agent's choices.
- Alternative: per-job modes. That is noisier and the user is unlikely to change it mid-conversation.
- Alternative: a session or user-level setting. That is coarser and does not let an individual conversation be manual while others are auto.

**Queue tool calls for manual approval in the worker.** When a tool call arrives and the permission mode is manual, the worker:
1. Emits a `tool` event with `status: awaiting_approval`.
2. Enqueues the tool call with its `toolCallId`, tool name, and arguments.
3. Polls the approval queue with a timeout.
4. If approved before timeout, emits `approved` and runs the tool.
5. If denied before timeout, ends the turn with an `error` event.
6. If timeout, treats it as a denial (the user walked away).

A client that wants to stay connected can watch `/api/jobs/{job_id}/events` and hit `/api/approvals/{job_id}/{toolCallId}` or `DELETE` to approve or deny.
- Alternative: stream approvals back in the job events. That makes the event stream bidirectional and couples the approval UI to the job stream.
- Alternative: a separate approval event stream. That adds complexity for a parallel concern.
- Alternative: pause the agent and wait in the request. That blocks the worker until approval arrives.

**Give manual mode a timeout.** If the user does not approve or deny in, say, 2 minutes, treat it as a denial and end the turn with a helpful error. This keeps jobs from hanging.
- Timeout is configurable as `AGENT_MANUAL_APPROVAL_TIMEOUT` (default 120 seconds).

**Use separate statuses for tool flow.** Tool events in manual mode show `awaiting_approval` → `approved` → `running` → `completed`, or `awaiting_approval` → `denied` (which ends the turn). This is clearer than reusing `running`.
- Alternative: only show the final status. That loses visibility into the decision.

**Plan mode is stubbed out.** It accepts `permission: plan` and places it in the database, but behaves like manual mode for now. The implementation comes later.

## Risks / Trade-offs

- **Approval latency.** If the user is not watching, tool calls wait for the full timeout. The default 2 minutes is generous.
- **Lost context.** If a conversation is long and a tool approval times out, the turn ends with an error. The agent sees the same history on the next message, but the momentum is lost.
- **Complexity in the worker.** Tool call queueing adds async state management to the worker loop.

## Open Questions

- **Which default mode should new conversations start in?** The proposal suggests the user picks it, with `auto` as the global default for new users.
- **Should approval mode integrate with the inbox, or is the approval queue separate?** The design assumes separate for now, and `add-inbox` will decide.
- **Should a denied tool call be retryable?** Or does it end the turn? The design ends the turn for simplicity.
