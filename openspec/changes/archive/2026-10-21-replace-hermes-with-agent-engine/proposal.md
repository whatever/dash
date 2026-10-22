## Why

dash answers every message by forwarding it to hermes-agent, which runs the agent loop, the tools, the terminal and the turn history in its own pod. dash only sees what hermes streams back. That costs three things:
- dash cannot gate a tool call hermes does not ask about. Its default "smart" approval mode approves risky commands with a model call.
- The history lives in hermes, so a failed turn leaves an empty reply that breaks the conversation, and dash cannot inspect or repair it.
- Every new capability, such as an inbox, approvals that wait for a person, or per-tool rules, has to go through another program's protocol.

Running the agent inside the dash worker on Pydantic AI gives dash the loop, the tools and the history, in about the amount of code `hermes.py` and its deploy footprint take today.

## What Changes

- **BREAKING:** hermes-agent is removed. Replies come from an agent that runs inside the worker, on the model named by `AGENT_MODEL`. The `HERMES_*` settings, the hermes deployment, its SSH server and its dashboard are gone.
- The worker keeps each conversation's full turn history, including tool calls and results, in Postgres. A failed turn leaves the history as it was.
- Old conversations carry on. Their first turn after the upgrade is seeded from the stored user and assistant messages.
- A running turn can be stopped. Every turn has a budget of model requests and tool calls.
- The agent gets tools of its own:
  - commands in the existing `dash-sandbox` pod, over SSH, where the Nango and GitHub tokens stay;
  - fetching a web page;
  - web search, with the model's own search or DuckDuckGo;
  - searching and adding memories;
  - any configured MCP server, such as the Serena sidecar.
- Each tool is set to `never`, `ask` or `auto`. `never` hides it from the model, and `auto` runs it. `ask` is defined by the `add-inbox` change.
- Job events keep their kinds and fields, so the web UI and stored replies render as before. Errors begin `agent:` instead of `hermes:`.

## Capabilities

### New Capabilities

- `agent-tools`: what the agent can do during a turn (sandbox commands, web fetch and search, memory tools, MCP servers) and how the per-tool policy applies.

### Modified Capabilities

- `chat`: replies come from the in-process agent, which keeps the turn history, can be stopped and has a budget. The event stream is unchanged apart from the error prefix.
- `memories`: recalled memories go into the agent's instructions, as the code already does. The baseline wrongly said "system message".

## Impact

- Code:
  - Removed: `hermes.py` and the `HERMES_*` settings.
  - Added: a `dash.agent` package (engine, history, tools, sandbox, policy) and a migration for the turn history.
  - Changed: `worker.py` and `__init__.py` wiring, a stop route in `web.py`, and the tests.
- Dependencies: `pydantic-ai-slim` with the `openai`, `bedrock`, `mcp` and `duckduckgo` extras. Every new package is MIT, Apache-2.0, BSD, ISC or Unlicense. The image gains `openssh-client`.
- Operators:
  - The chart no longer deploys hermes: no `templates/agent/*`, no `hermes.*` values, no `dash-hermes` secret.
  - The worker mounts the sandbox SSH key, and the sandbox NetworkPolicy admits `dash-worker` instead of `dash-agent`.
  - New settings: `AGENT_MODEL`, `AGENT_BASE_URL`, `AGENT_API_KEY`, `AGENT_THINKING`, the turn limits, `SANDBOX_*`, `AGENT_MCP_SERVERS`, `AGENT_TOOL_POLICY` and `AGENT_WEB_SEARCH`.
- Cost: one fewer pod (hermes requested 1 Gi and was limited to 4 Gi). Model usage is about the same, and each turn is now capped.
- Open PRs:
  - #26 (PR review webhook) calls the chat handler and needs its review job moved onto the engine.
  - #31 (Serena sidecar) configures hermes's `mcp_servers` and becomes an `AGENT_MCP_SERVERS` entry.
