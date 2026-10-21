## 1. Engine

- [x] 1.1 Add `pydantic-ai-slim` with the `openai`, `bedrock`, `mcp` and `duckduckgo` extras, and check each new dependency's licence. Verify: `uv lock` succeeds, and no new dependency is copyleft.
- [x] 1.2 Build the agent from `AGENT_MODEL`, `AGENT_BASE_URL` and `AGENT_API_KEY`, with memories as per-turn instructions. Verify: unit tests for a Bedrock model string, an OpenAI-compatible URL, and memory instructions present or absent.
- [x] 1.3 Map `run_stream_events` onto `delta`, `reasoning` and `tool` events, keeping the 48-character batching and the stored trail. Verify: `FunctionModel` tests cover text that arrives in a part's start event, a replaced part, thinking, and a tool call with its label, and assert the exact events and trail.
- [x] 1.4 Replace the `Chat` protocol in the worker with the engine, and end failed turns with `agent:` errors. Verify: worker tests for success, failure, nothing to answer, and memories extracted only after success.

## 2. History, stop and budget

- [x] 2.1 Add a migration for one stored `Conversation` per conversation, deleted with it. Verify: the offline migration test renders the table, and there is a single head.
- [x] 2.2 Load the history before a turn, save it only when the turn ends, and seed conversations that have none from their stored messages. Verify: tests for a follow-up turn that sees the earlier tool result, a failed turn that leaves the history unchanged, and a seeded old conversation.
- [x] 2.3 Add `POST /api/jobs/{job_id}/stop`, and have the worker cancel the run within 2 seconds. Verify: API and worker tests that a stopped turn stores the partial reply and its history and ends with `done` and `stopped` true.
- [x] 2.4 Apply `AGENT_REQUEST_LIMIT` and `AGENT_TOOL_CALL_LIMIT`. Verify: a `FunctionModel` that loops on a tool ends with an error naming the limit.

## 3. Tools and policy

- [x] 3.1 Add `run_command` over the system `ssh` binary, with the 90-second timeout and the 20,000-character cap. Verify: tests with a fake subprocess for success, a non-zero exit, a timeout and long output, plus the exact `ssh` arguments.
- [x] 3.2 Add `fetch_url` with the address check on the first request and every redirect. Verify: tests with `httpx.MockTransport` and a fake resolver for a public page, `127.0.0.1`, `10.x` and a redirect to an internal address.
- [x] 3.3 Offer web search through the model's own search or DuckDuckGo, unless `AGENT_WEB_SEARCH` is `off`. Verify: on the local stack, a search question is answered through `duckduckgo_search`.
- [x] 3.4 Add `search_memories` and `remember`. Verify: tests with the fake store and embedder for a stored fact, a repeat, and the search results.
- [x] 3.5 Load MCP servers from `AGENT_MCP_SERVERS` with prefixes and exclusions, and skip a server that is down, with a `status` event. Verify: tests with an in-process MCP server and one that refuses connections.
- [x] 3.6 Apply `AGENT_TOOL_POLICY`, including `<server>_*`, and hide `never` tools. Verify: tests that `never` hides a single tool and a whole server, and unlisted tools stay `auto`.

## 4. Deploy

- [x] 4.1 Remove `hermes.py`, the `HERMES_*` settings and their wiring, and add the `AGENT_*` and `SANDBOX_*` settings. Verify: `grep -ri hermes src tests` finds nothing, and the README settings table lists the new names.
- [x] 4.2 Compose: remove the `hermes-agent` and `hermes-seed` services, give the worker the sandbox SSH key, and rename the LiteLLM alias. Verify: `docker compose up` answers a chat and runs `git --version` in the sandbox.
- [x] 4.3 Chart: remove `templates/agent/*`, `files/hermes-config.yaml`, `files/sshd/*`, the `hermes.*` values and the `dash-hermes` secret. Mount the sandbox key and the Bedrock credentials into the worker, and let the sandbox NetworkPolicy admit `dash-worker`. Verify: `helm template` renders with default and local values, and has no hermes objects.
- [x] 4.4 Add `openssh-client` to the image. Verify: the image builds, and `ssh -V` runs in it.
- [x] 4.5 Update the README and the UI copy that mention hermes. Verify: no user-facing text names hermes.

## 5. Checks

- [x] 5.1 Run the repo checks. Verify: `uv run ruff check`, `uv run ruff format --check`, `uv run pyright` and `uv run pytest` pass.
- [x] 5.2 Validate the change. Verify: `openspec validate replace-hermes-with-agent-engine --strict` passes.
