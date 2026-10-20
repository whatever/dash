## Context

`/healthz` returns `{"status": "ok"}` without touching anything. The chart uses it for both the readiness and the liveness probe of the API pod. Postgres and Redis have their own pod probes, but nothing reports to a client that the API cannot reach them. The worker has no HTTP endpoint and no probe.

## Goals / Non-Goals

**Goals**
- One request tells an operator whether the API can serve real work.
- A dependency outage never restarts the API pod.

**Non-Goals**
- Checking the Hermes agent, Nango or the sandbox. They are separate services with their own probes.
- Worker health. See the open questions.
- Metrics, tracing or a status page.

## Decisions

**A second endpoint, not a deeper `/healthz`.** Liveness answers "should the kubelet restart this process"; restarting cannot fix a database that is down, and a restart loop during an outage makes recovery slower. Readiness answers "can it do work right now", and a failed readiness probe only takes the pod out of the Service.

**Check by doing the cheapest real operation.** `SELECT 1` on a pooled connection and Redis `PING`. The engine already uses `pool_pre_ping`, so this exercises the same path as a real request.

**A short timeout per check.** Each dependency gets 2 seconds, and the two run concurrently, so a hung connection reports as failed rather than hanging the probe past its own timeout.

**Name the dependency, not the error.** The body lists `database` and `redis` as `ok` or `failed`. Exception text can include hostnames or credentials from the connection string, and dash has no authentication of its own.

## Risks / Trade-offs

- A flapping Redis marks the API unready, so the Service drops it. With one API replica that is a full outage for the web UI, but the UI cannot do anything useful without Redis anyway.
- `/readyz` costs two round trips per probe. At a probe every 10 seconds that is negligible.

## Open Questions

- The worker consumes the Redis stream but exposes nothing, so a wedged worker looks healthy. Options: a heartbeat key the worker refreshes and `/readyz` reads, or a small HTTP port on the worker.
- Should `/readyz` also report the queue backlog from `Queue.status()`? It is informational, not a pass or fail.
