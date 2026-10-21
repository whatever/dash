## Context

**The worker today.** A chat job loads the conversation, recalls memories, and calls `Hermes.stream()`. That posts the newest user message to hermes's `/v1/responses` under the conversation name `dash:<id>`, and the worker parses hermes's server-sent events into `Delta` values. `handle_chat` batches them into job events (`delta`, `reasoning`, `tool`, `status`, `memories`), stores the reply with its event trail, ends with `done`, and extracts memories. The web UI renders those event kinds and replays the stored trail.

**Hermes.** It runs as its own pod with a 20 Gi volume, an sshd for operators and an optional dashboard ingress. It reaches the `dash-sandbox` pod over SSH, and only that pod holds the Nango and GitHub tokens. Hermes keeps every turn's history, tool calls included, and dash never sees it.

**Pydantic AI 2.58.0.** These are the parts this design uses, read from the released package:
- `Agent.run_stream_events` streams text, thinking and tool events in one pass.
- `Conversation` and `ConversationTypeAdapter` persist a conversation's messages, usage and pending approvals as JSON.
- `UsageLimits` caps requests and tool calls.
- `CancellationToken` stops a run and keeps its history.
- Toolsets can be filtered, prefixed and wrapped.
- `MCPToolset` connects to MCP servers.
- `TestModel` and `FunctionModel` run an agent in tests without a model.
- Models come from Bedrock, Anthropic, OpenAI-compatible APIs and LiteLLM.

## Goals / Non-Goals

**Goals**
- dash owns the agent loop, the tools and the turn history. hermes is removed completely.
- The web UI keeps working unchanged: same event kinds, same fields, same stored trail.
- Every tool call goes through dash, so a per-tool policy applies to all of them.
- The sandbox, its token sidecars and its network boundary stay as they are.

**Non-Goals**
- Approvals that wait for a person. They come with the `add-inbox` change.
- Handing work to an outside agent over ACP, such as hermes or Claude Code. That is a later change, and would come back as one tool.
- Push notifications, multiple users, or a skills system like hermes's `SKILL.md` files.
- Changing memory extraction or the Bedrock memory models.

## Decisions

**Run the agent in the worker with Pydantic AI.** It is the tool-calling loop with typed tools, dependencies and output, plus streaming, history, limits, cancellation and test models, under an MIT licence.
- Alternative: keep hermes and drive it over ACP, as the October spike did. Hermes still decides which calls to ask about, `curl` and `git push` never ask, and each live session costs about 236 MB.
- Alternative: the OpenAI Agents SDK or LangGraph. The first is built around OpenAI's APIs, and the second is a graph framework that would wrap the same loop with more machinery.
- Alternative: a hand-written loop, as HexisPro's `AgentLoop` is. It re-implements streaming, retries and provider quirks for no gain.

**Stream with `run_stream_events` and map onto today's event kinds.**
- Text parts become `delta` and thinking parts become `reasoning`. The first chunk of a part arrives in its start event and has to be emitted too. A repeated start for the same part index replaces that part rather than appending to it.
- A tool call becomes `tool` with `status: running` and a 120-character `label` from its arguments, as hermes's labels were built. Its result becomes `tool` with `status: completed`.
- The worker keeps its 48-character batching and trail recording.
- Alternative: `iter()` and per-node streams. That is more code for the same events. `run_stream()` stops at the first output and skips later tool calls, so it can't be used here.

**Keep the turn history as one `Conversation` row per conversation, written when a turn ends.** It holds the model messages, the running usage and any pending approvals. Pending approvals can't be rebuilt from messages, so the next change needs this.
- A failed turn writes nothing, so the conversation's history stays as it was.
- A stopped turn writes the partial history the library hands back. It closes any unfinished tool call as interrupted.
- Alternative: store only the message list. That drops usage and pending approvals.
- Alternative: rebuild the history from the `messages` table every turn. That loses tool calls and results.

**Seed old conversations from their stored messages.** A conversation with no stored history starts its first turn with its user and assistant messages as plain text, so the upgrade keeps the thread. Tool calls from the hermes era are not recoverable. They were never stored in dash.

**Name the model with `AGENT_MODEL`.** It takes a Pydantic AI model string. The default `bedrock:global.anthropic.claude-opus-5-5` matches the model the chart's hermes used. When `AGENT_BASE_URL` is set, the name goes to that OpenAI-compatible API (LiteLLM, OpenRouter) through `LiteLLMProvider`, with `AGENT_API_KEY`. Compose keeps its LiteLLM proxy, so local development needs no AWS account.
- Alternative: keep the `HERMES_MODEL` alias names. They describe a router that no longer exists.

**Run sandbox commands with the system `ssh` binary.** One `ssh` per command, as `agent@SANDBOX_HOST`, running `cd /config/workspace && <command>`. It uses the mounted key, with `BatchMode=yes`, a 90-second timeout and output capped at 20,000 characters. This is what hermes's SSH backend did, so the sandbox image, its keys, its token sidecars and its NetworkPolicy stay as Matt built them. The only change is that the policy admits `dash-worker`.
- Alternative: a small HTTP exec server inside the sandbox pod. It needs no SSH key, but it is a new component to secure.
- Alternative: an SSH client library such as asyncssh. That adds a dependency with a copyleft licence to a public-domain project.

**Fetch pages with a small tool of our own.** It uses `httpx`, already a dependency, and refuses any address that resolves to a private, loopback, link-local or reserved range. That check runs again on every redirect, with at most 5 redirects. The body is capped at 1 MB, and the text returned at 20,000 characters.
- Alternative: Pydantic AI's `web-fetch` extra. That adds dependencies for something the tool does in about 40 lines.

**Search the web with the model's own search, or DuckDuckGo.** Pydantic AI's `WebSearch` capability uses the provider's native search where the model has one. Neither Bedrock Converse nor an OpenAI-compatible chat API through LiteLLM has one, so in practice the worker runs a DuckDuckGo search (`ddgs`, MIT). It needs no API key. `AGENT_WEB_SEARCH=off` removes search.
- Alternative: offer search only where the model has it natively. With dash's models that means no search at all, which is less than hermes offered.
- Alternative: a keyed search API such as Tavily or Exa. It is better quality, but it adds an account and a secret.

**Read the tool policy from configuration.** `AGENT_TOOL_POLICY` is a JSON map from tool name to `never`, `ask` or `auto`. MCP tools are named `<server>_<tool>`, and `<server>_*` sets a whole server. Unlisted tools are `auto`. `never` removes a tool with a filtered toolset, so the model never sees it.
- Alternative: rules in the database, edited from the UI. Saved "always allow" rules arrive with the inbox, and a full editor can follow once the shape has settled.
- Until `add-inbox` lands, an `ask` tool is hidden like a `never` one, so nothing set to `ask` runs unasked.

**Stop a turn through Redis.** `POST /api/jobs/{job_id}/stop` sets a key. The worker checks for it while streaming and cancels the run's token.
- Alternative: pub/sub. It adds a subscription per turn for one bit of state.

**Budget every turn.** `AGENT_REQUEST_LIMIT` (default 30) caps model requests and `AGENT_TOOL_CALL_LIMIT` (default 50) caps tool calls. A turn that would exceed either ends with an `error` event.

## Risks / Trade-offs

- **Hermes's extras are lost.** Its `SKILL.md` skills, memory files, session search, todo list and delegation go with it. The tools above cover what dash's chart enabled, apart from skills and todo. Any skill a user relied on has to come back as instructions or a tool.
- **The worker holds the sandbox SSH key.** A compromised worker can run commands in the sandbox. The hermes pod could do that today, and the worker never gets the tokens themselves.
- **History grows with every tool result.** Long conversations will reach the model's context limit. Mitigation: a history processor that trims old tool results. If that isn't enough, a later change can summarise old turns.
- **Duplicated text** is the classic streaming mapping bug. The event contract tests pin it down, both for text that arrives inside a part's start event and for a part that is replaced.
- **One model per deployment.** A model that can't call tools, or a provider outage, stops every reply. A fallback model is possible later.

## Open Questions

- **Matt: is the SSH binary the transport you want?** It keeps your sandbox untouched. An HTTP exec server would remove the SSH key from the worker.
- **Matt: did anyone use the hermes dashboard ingress?** This change removes it, and nothing in dash replaces it.
- **Matt: should the default model stay Bedrock Opus?** Everything else in dash is model-agnostic now.
- **#26: who moves its review job onto the engine?** The PR review webhook calls the chat handler, so whichever lands second ports it. It is one call.
