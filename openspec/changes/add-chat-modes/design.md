## Context

Approvals today are decided per tool, globally: a policy marks a tool `never`, `ask` or `auto`, and a saved rule lets an `ask` tool run unasked. That suits one person running one kind of chat. It does not let two chats differ, and it has no middle ground between asking about everything and about nothing.

## Goals / Non-Goals

**Goals**
- Let one conversation ask more or less than another.
- Keep today's behaviour as the default.
- Keep `never` meaning never.

**Non-Goals**
- Per-user or per-organisation modes. A conversation is the unit here.
- Choosing the classifier model or its prompt. `auto` states the contract, not the implementation.
- Replacing the deployment policy. It stays the base that modes adjust.

## Decisions

**A mode adjusts the base policy; it does not replace it.** `never` tools are hidden in every mode, so an operator can still remove a tool for good. A mode only changes whether an `ask` or `auto` tool asks.
- Alternative: modes replace the policy entirely. That makes `dangerously_skip` able to expose tools an operator hid.

**The default is `fast_forward`.** It matches how chat works now, so existing conversations do not change behaviour.

**`auto` fails closed.** If the classifier errors, times out or is unsure, the call asks. A deterministic list of calls that always ask runs before the classifier and cannot be overridden by it.

**`plan` is a state, not a tool.** Until a plan is approved, tools with side effects are withheld from the model. Read-only tools stay available so it can investigate.
- Alternative: expose a `plan` tool the model calls. Products differ here, some appending plan instructions to the prompt and some using a tool, and the choice should follow research.

**A mode change applies from the next turn.** A turn already running, and approvals already open, are not changed. This avoids a turn that started under one mode finishing under another.

## Risks / Trade-offs

- **`dangerously_skip` is a footgun.** It needs to be explicit per conversation and visibly marked in the UI. An operator setting to disable it is worth considering.
- **`auto` is only as good as its classifier.** A wrong "safe" verdict runs a call nobody saw. Recording the verdict on the approval item lets a person audit it.
- **A broad allow rule turns `fast_forward` into `dangerously_skip` for that tool.** A rule on `run_command` approves every shell command. Conditions on rules may be needed.

## Open Questions

- Is the mode a property of the conversation, of the user, or a user default with a per-conversation override?
- When the mode changes while approvals are open, should they stay open, or resolve under the new mode?
- Does approving a plan switch the conversation to another mode, and which one?
- Which tools count as read-only for `plan`, and who decides: the tool author or the policy?
- Should `dangerously_skip` be disableable by an operator setting?
- What belongs on the always-ask list for `auto`, and is it configurable?
