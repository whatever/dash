## Why

`GET /healthz` answers `ok` whenever the API process is running, so it stays green while Postgres or Redis is down, and every `update` job and chat message fails. An operator watching a dashboard or an uptime probe sees a healthy dash that cannot do anything. The same endpoint is the pod's liveness probe, so it cannot start checking dependencies without making a database blip restart the API.

## What Changes

- Add `GET /readyz`. It reports whether the database and Redis answer, and returns 503 naming whichever does not.
- Keep `GET /healthz` as it is: process up, no dependencies. Document that as the liveness contract.
- The chart's readiness probe moves to `/readyz`. The liveness probe stays on `/healthz`.
- No change to chat, sources or memories. Nothing is **BREAKING**.

## Capabilities

### New Capabilities

- `health`: what the liveness and readiness endpoints report and when each fails.

### Modified Capabilities

None.

## Impact

- Code: `web.py` (the route), `db.py` and `queue.py` (a cheap ping each), the chart's API readiness probe, and tests.
- Operators: an external probe can point at `/readyz` to see a broken dependency. Existing probes on `/healthz` behave as before.
