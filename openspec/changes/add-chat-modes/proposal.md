## Why

Every conversation shares one approval policy: `AGENT_TOOL_POLICY` says which tools ask, and "Always allow" adds a global rule. Running several chats at once showed the gap. A throwaway experiment wants nothing to ask, a chat that touches real repositories wants everything to ask, and neither can be set without editing the deployment for all chats.

This change proposes a mode per conversation that decides how tool approvals behave. It is a proposal to discuss, not a settled design: the modes below are the ones that came up, and the open questions in `design.md` are the ones to answer before building.

## What Changes

- Add a `mode` to each conversation: `manual`, `fast_forward`, `auto`, `plan` or `dangerously_skip`.
- `manual`: every tool call asks.
- `fast_forward`: calls to tools with a saved allow rule run; the rest ask. This is how chat behaves today, so it is the default.
- `auto`: a classifier decides whether a call asks, with a deterministic list that always asks.
- `plan`: the agent investigates and proposes a plan, and tools with side effects do not run until a person approves it.
- `dangerously_skip`: nothing asks.
- A client can read and change a conversation's mode. A change applies from the next turn.
- Nothing is **BREAKING**: existing conversations are `fast_forward`.

## Capabilities

### New Capabilities

- `chat-modes`: the modes, what each does to tool approvals, and how a mode is read and changed.

### Modified Capabilities

None. This change is written against the approval flow proposed in the agent engine and inbox changes (whatever/dash#36 to #40). It refers to their ideas, not their specs, so it can be read and validated on its own. Once they land, the requirements that mention approvals should be reconciled with the `inbox` and `agent-tools` specs.

## Impact

- Code: the conversation table (a mode column), the tool policy check, the chat API and UI (a mode control), and for `auto` a classifier call.
- Operators: `AGENT_TOOL_POLICY` keeps its meaning as the base policy. `never` tools stay hidden in every mode.
- Security: `dangerously_skip` and `auto` widen what runs without a person. Both are opt-in per conversation, and neither is a deployment default.
