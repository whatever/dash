# dash

An always-on assistant. Its agent runs inside the worker on [Pydantic AI](https://ai.pydantic.dev).

| Part | What it does |
|---|---|
| Web UI (`src/dash/static`) | Chat, memories (list, search, add, delete), connected apps, and queue status. No build step. |
| API (`dash serve`) | FastAPI. Stores each user message, then adds a job to the Redis stream `dash:jobs`. |
| Worker (`dash worker`) | Reads `dash:jobs`, recalls memories from pgvector, runs an agent turn and streams it. Each conversation's turn history, tool calls included, is stored in Postgres. Then it extracts new memories. |
| Memories | Postgres + pgvector. Bedrock Titan v2 makes the embeddings. Bedrock Haiku extracts the facts. |
| App keys | A self-hosted [Nango](https://nango.dev). Nango holds the OAuth tokens. The sandbox reads them, so the agent never sees the Nango key. |
| GitHub (`src/dash/github`) | Creates a private GitHub App from a manifest and stores its keys in the `authorizations` table. Use `app_client` and `installation_client` to call GitHub. |

The browser follows a reply through `GET /api/jobs/<id>/events` (SSE). The worker writes each reply to its own Redis stream, so a page reload replays the reply from the start.

## Run locally

The compose stack runs everything, Nango included. Nango needs `NANGO_ENCRYPTION_KEY` in `.env`. Make it with `openssl rand -base64 32`.

```sh
cp .env.example .env   # then set NANGO_ENCRYPTION_KEY
just docker up         # also: just docker down, nuke, logs [service], ps
```

Then open http://localhost:8000 (dash) and http://localhost:3003 (Nango, user `admin`). See `compose.yaml` for the other ports.

To run dash outside Docker:

```sh
docker run -d --name pg -p 5432:5432 -e POSTGRES_PASSWORD=dash pgvector/pgvector:pg16
docker run -d --name redis -p 6379:6379 redis:8-alpine
export DATABASE_URL=postgresql://postgres:dash@localhost:5432/postgres
export AGENT_MODEL=bedrock:global.anthropic.claude-opus-5-5   # or AGENT_BASE_URL=... AGENT_MODEL=<name>
uv run dash migrate
uv run dash worker &
uv run dash serve
```

To run the Helm chart (`charts/dash`) on Rancher Desktop (dockerd runtime, Traefik on):

```sh
just up                # builds dash:local, writes .local/secrets.json from .env, installs the chart
just ps                # also: just logs [-f] <deployment>, just scrape, just down, just nuke
```

Then open http://dash.localhost. `values-local.yaml` swaps RDS for an in-cluster pgvector and the ExternalSecrets for plain Secrets. The `dash-bedrock` Secret needs `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in `.env`. With no values, `helm template` renders the prod objects from `geometry.dev/apps/dash`.

The worker needs AWS credentials for Bedrock in the standard env chain. Outside Docker, Nango is optional. To use it, set `NANGO_URL` and `NANGO_SECRET_KEY`.

## GitHub

In the Apps tab, click **Create GitHub App**. Type an organization, or leave it empty for your personal account.

1. dash sends a manifest to GitHub. The manifest has the name, permissions, and redirect URLs.
2. On GitHub, you confirm the app. GitHub sends you back to `/github/callback` with a code.
3. dash exchanges the code for the app ID, private key, client secret, and webhook secret. Then it stores them.
4. GitHub opens the install page. After you install, `/github/setup` copies the installations from GitHub.

dash stores the private key and secrets as plain JSONB. Protect the database.

## Settings

| Env var | Default |
|---|---|
| `DATABASE_URL` | (required) |
| `REDIS_URL` | `redis://localhost:6379/0` |
| `PUBLIC_URL` | Browser-facing dash address for GitHub redirects. Empty means the request address. |
| `AGENT_MODEL` | `bedrock:global.anthropic.claude-opus-5-5`. A Pydantic AI model string, or a model name at `AGENT_BASE_URL`. |
| `AGENT_BASE_URL`, `AGENT_API_KEY` | Empty. An OpenAI-compatible `/v1` URL (LiteLLM, OpenRouter) and its key. |
| `AGENT_THINKING` | Empty (the model's default). `minimal`, `low`, `medium`, `high` or `xhigh`. |
| `AGENT_REQUEST_LIMIT`, `AGENT_TOOL_CALL_LIMIT` | `60`, `100`. Each turn gets its own budget, and a turn that would go past either ends with an error. |
| `AGENT_TOOL_POLICY` | Empty (every tool `auto`). A JSON object from a tool name, or `<server>_*`, to `never`, `ask` or `auto`. An `ask` call waits in the Inbox until someone allows or denies it. The chart sets `{"run_command": "ask"}`. |
| `AGENT_MCP_SERVERS` | Empty. A JSON list of `{"name", "url", "exclude"}`: streamable-HTTP MCP servers whose tools the agent gets, named `<name>_<tool>`. |
| `AGENT_WEB_SEARCH` | `on`: the model's own web search, or DuckDuckGo. `off` removes it. |
| `SANDBOX_HOST`, `SANDBOX_PORT`, `SANDBOX_USER`, `SANDBOX_KEY_PATH` | Empty (no `run_command` tool), `2222`, `agent`, `/run/secrets/sandbox/id_ed25519`. Where `run_command` runs, over ssh. |
| `NANGO_URL`, `NANGO_SECRET_KEY` | `http://localhost:3003`, empty (disabled) |
| `NANGO_PUBLIC_URL`, `NANGO_CONNECT_URL` | Browser-facing Nango API and Connect UI addresses |
| `EMBED_MODEL`, `EXTRACT_MODEL`, `MEMORY_TOP_K` | Titan v2, Haiku 4.5, `8` |

## Deploy

ArgoCD deploys dash from the Kustomize manifests in [`whatever/geometry.dev/apps/dash`](https://github.com/whatever/geometry.dev/tree/main/apps/dash). They run the API, the worker, Redis (AOF), Nango, ExternalSecrets, and the Traefik ingress. `compose.yaml` is the reference for these parts.

On each push to `main`, CI does these steps:
1. It publishes the image `ghcr.io/whatever/dash:sha-<short>`.
2. It sends an `image-published` dispatch to geometry.dev.
3. geometry.dev opens a PR that bumps the image tag in `apps/dash`.
4. When that PR merges, ArgoCD syncs the new image.

CI needs the `GEOMETRY_BUMP_CLIENT_ID` variable and the `GEOMETRY_BUMP_APP_KEY` secret. The GitHub App must be installed on geometry.dev with contents write access.

Before the first sync, do these steps:
1. On RDS, as the master user, create the `dash` and `nango` databases. Then run `CREATE EXTENSION vector` in `dash`.
2. Add `DASH_DATABASE_URL` and `NANGO_DATABASE_URL` to `geometry/config`.
3. Create `geometry/dash` with `NANGO_ENCRYPTION_KEY` and `NANGO_DASHBOARD_PASSWORD`. Make the key with `openssl rand -base64 32`. Do not rotate it.
4. After Nango starts for the first time, copy `NANGO_SECRET_KEY` from its dashboard into `geometry/dash`.


## Checks

```sh
uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest
```
