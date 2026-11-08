## Why

An operator cannot see what dash did on a person's behalf: which model calls a turn made, what each tool call did, how long and how many tokens it cost, or why a job failed. Logs say a job ran and nothing more. A governance or research setup needs traces it can group by conversation and send to a self-hosted backend such as Phoenix or Langfuse without dash knowing which one.

## What Changes

- Add OpenTelemetry tracing to the API, the worker and the scrape command, exported over OTLP.
- Trace every model call: chat turns, tool calls, embeddings, memory fact extraction and fact extraction from source updates. Each carries the model name and token usage when the provider reports it.
- Group spans by conversation, so a backend shows one session per chat, and follow a job from the request that queued it into the worker.
- Capture prompt and completion text only when the operator turns it on.
- Do nothing at all when no OTLP endpoint is set.
- Run an OpenTelemetry Collector beside the stack in compose and the chart, so dash exports to one place and the operator picks the backends.

## Capabilities

### New Capabilities

- `telemetry`: what dash exports, how an operator configures it, and what it never exports by default.

### Modified Capabilities

None.

## Impact

- Code: a telemetry module started by the API, the worker and `dash scrape`; spans around the memory and source model calls; trace context in the queued job; new dependencies `opentelemetry-sdk` and `opentelemetry-exporter-otlp-proto-http` (Apache-2.0).
- Operators: new optional `OTEL_*` and `TELEMETRY_CAPTURE_CONTENT` settings, a collector service in compose, and `telemetry.*` chart values. Nothing changes when they are unset.
- Out of scope: choosing or deploying a backend (Phoenix, Langfuse), metrics and logs export, evals, and dashboards.
