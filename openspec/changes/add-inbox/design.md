## Context

After `replace-hermes-with-agent-engine`, the worker runs a Pydantic AI agent and stores each conversation's `Conversation` (messages, usage and any pending tool requests) when a turn ends. The tool policy hides `never` tools and runs `auto` ones. `ask` has no behaviour yet.

Pydantic AI supports approvals in two library pieces:
- A tool wrapped by `ApprovalRequiredToolset` raises `ApprovalRequired` when a function of `(ctx, tool_def, args)` returns true. The run then ends with a `DeferredToolRequests` output, which lists the waiting calls.
- A later run continues the same conversation with `deferred_tool_results`, which maps each call id to `ToolApproved` or `ToolDenied`. It may also carry a new user prompt in the same run.

The October ACP spike built approvals the other way: the agent blocked for at most 300 seconds while a person answered. It also found that saving "always allow" rules by tool kind became a blanket allow.

## Goals / Non-Goals

**Goals**
- A person can answer an approval minutes or days later, and the turn continues where it stopped.
- "Allow always" never widens past the exact call that was approved.
- The agent can leave a non-action note that outlives the chat it came from.
- Answering never needs the reply's page to be open.

**Non-Goals**
- Push notifications to a phone, Slack or email. The inbox is the delivery point for now.
- Editing saved rules in the UI. Rules can be listed and deleted through the API only.
- Approvals for outside agents over ACP.

## Decisions

**End the turn instead of waiting.** An `ask` call makes the run end with `DeferredToolRequests`. The worker stores the reply so far as an assistant message, saves the `Conversation` (it carries the pending requests), opens one approval item per call, and ends the job with `done` and the waiting item ids. Nothing runs while a person decides.
- Alternative: block the worker on an answer, as the spike did. That ties up a worker slot, loses the turn on a restart, and forces a timeout far shorter than people take to answer.

**Resume once every approval from a turn has a decision.** The library continues a turn with results for all of its waiting calls. So the `resume` job is queued when the last open approval from that turn is answered, and the answer that completes the set returns its `job_id`. The resume job builds `ToolApproved` or `ToolDenied` for each call and streams a new assistant message with the usual events.
- Alternative: resume after each answer, with partial results. That turns one turn into several model calls that each see a half-answered state.

**Key rules on the tool name.** "Allow always" stores the tool name. The approval check runs before every `ask` call, reads the rules at the start of each turn, and skips asking when a rule names the tool. Rules are global, so one answer holds in every conversation.
- Alternative: match the tool and its exact arguments. The first version did, and it asked again for every command that differed, so approvals piled up. It was the cause of repeated prompts across chats.
- Alternative: scope rules to a conversation. Safer, but the same tool is approved again in each new chat.
- The spike showed that a rule by tool kind becomes a blanket allow. For `run_command` that is a standing approval of every shell command. The rules list and `DELETE /api/inbox/rules/{id}` are the way back, and a person can keep `run_command` on `ask` and answer with plain `allow`.

**A new message denies what is still open.** If the person writes instead of answering, the open approvals from that conversation are resolved as `denied` with reason `superseded`. The new turn sends their denials and the new message in one run, which the library supports. The model hears both, and the conversation never has calls left unanswered.

**Expire after 24 hours, lazily.** A sweep in the worker loop marks approvals older than 24 hours as `expired`. Expired calls are sent as denied on the conversation's next turn, so nothing is resumed unprompted.

**Messages are a tool the policy covers.** `leave_message` is an ordinary tool. Setting it to `never` stops the agent leaving notes, and `ask` makes each note an approval first. It takes a title (at most 120 characters), a body (at most 4,000) and up to 10 source URLs.

**One table for both kinds.** `inbox_items` holds both kinds, with `kind`, `status`, `title`, `body`, a JSON `data` (tool, arguments, call id and label for approvals; sources for messages), the conversation and job ids, and timestamps. `tool_rules` holds the saved rules.

**Poll for the badge.** The UI asks `GET /api/inbox/count` every 15 seconds and after every job ends. One small query per tab is cheaper than a second event stream.

## Risks / Trade-offs

- **A resumed turn runs on whatever model is configured then.** The model may have changed since the approval was raised. That is acceptable, because the history and the pending calls are stored in a model-neutral form.
- **A rule on the tool name is broad.** "Always allow" on `run_command` approves every later command. A pattern rule or a command allowlist can narrow it if this proves too loose.
- **Two surfaces answering the same item.** The inbox and the chat both show an approval. The second answer is a no-op that returns the first one's result, and the chat shows the card as answered.

## Open Questions

- Should denied approvals that were superseded or expired stay visible in the inbox, or be hidden by default? The spec keeps them listable with `status=all`.
- Is `{"run_command": "ask"}` the right default for the chart? It makes every sandbox command an approval, which is safe but noisy until rules accumulate.
