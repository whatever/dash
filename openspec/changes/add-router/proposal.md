## Why

Every inbound job is handled the same way for its kind:
- A `chat` job answers the conversation.
- An `update` job becomes a memory unless it nearly duplicates one.

Nothing decides whether an update is worth keeping, so a Hacker News front page puts every new item into memory next to what the person actually said. Live shows that a job arrived, but not what dash did with it or why. As more sources arrive (Slack, GitHub, cron, other agents), each would add a branch to the worker. Dash needs one place that decides what an inbound job is for.

## What Changes

- **Every job gets a routing decision.** The worker decides before it acts: an action, which stage decided, a confidence and a reason. The decision is stored on the job's timeline entry and listed by `/api/live`.
- **Rules first.** A chat job always routes to chat, with no model call. A source can carry a fixed `route` (`ignore`, `remember` or `flag`) that applies to all of its updates.
- **A cheap model triages the other updates** into `ignore` (not stored), `remember` (today's behaviour) or `flag` (stored, and marked as worth the person's attention). Item text is fenced as untrusted data.
- **Unsure or failed means today's behaviour.** A decision below `ROUTER_MIN_CONFIDENCE`, or a failed model call, falls back to `remember`, and the reason says so.
- **A `dash eval-router` command** measures the triage against labelled items.
- Live shows each decision.

Nothing is **BREAKING**. Until a source has a `route` or triage is turned on, every update is still remembered.

## Capabilities

### New Capabilities

- `router`: routing decisions for inbound jobs, the rules and model stages, the fallback, and the eval command.

### Modified Capabilities

- `chat`: timeline entries carry the job's decision.
- `sources`: a source can carry a fixed route, and an update job follows its decision instead of always storing a memory.

## Impact

- Code: a `router` module, the worker's job handling, a migration adding decision columns to `timeline` and `route` to `sources`, store methods, `/api/live`, the sources API, a CLI command, and Live in `static/`.
- Operators: `ROUTER_TRIAGE` (off by default) and `ROUTER_MIN_CONFIDENCE` (default 0.8).
- Cost: one call to the extraction model per update when triage is on. Chat jobs never call it.
- Out of scope:
  - routing replies back to a running session
  - asking the person when the router is unsure
  - starting work on other engines
  - budgets
  - new sources
- Migration numbering: `replace-hermes-with-agent-engine` and `add-inbox` also add migrations after `0005`. Whichever merges second renumbers its migration.
