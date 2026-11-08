## Context

dash has no tracing. The worker logs one line per job. Chat today goes through hermes; the open agent-engine stack ([dash #36](https://github.com/whatever/dash/pull/36) to [#40](https://github.com/whatever/dash/pull/40)) replaces it with an in-process Pydantic AI agent. Memory recall and fact extraction call Bedrock or an OpenAI-compatible API directly. [dash #33](https://github.com/whatever/dash/pull/33) adds fact extraction from scraped updates. The spec therefore names call sites by behavior, not by library, so it holds on every one of those branches.

## Decisions

### Export OTLP to a collector, not to a backend

dash sets only the standard `OTEL_EXPORTER_OTLP_*` variables. The collector receives OTLP and fans out to Phoenix, Langfuse or both. Switching or comparing backends is a collector config change, and dash never imports a vendor SDK. Both backends accept OTLP over HTTP, so the exporter is `opentelemetry-exporter-otlp-proto-http`.

### Off unless an endpoint is set

With no `OTEL_EXPORTER_OTLP_ENDPOINT` the module installs no provider, so spans are no-ops. Local development and tests pay nothing and need no collector.

### Call sites

- Agent turns: on the agent-engine branch, Pydantic AI's `Agent.instrument_all()` with `InstrumentationSettings` emits `gen_ai.*` spans for runs, model requests and tool calls. `include_content` is bound to `TELEMETRY_CAPTURE_CONTENT`. Hermes turns get one manual `chat.turn` span, since hermes has no hooks.
- Memory and source model calls go through boto3 or `httpx`, which Pydantic AI does not cover. Each gets a manual span with `gen_ai.*` attributes. Their content is captured only under the same flag.
- Approvals span turns: the turn stops, and a resume job runs later. The inbox row stores the trace context, and the resume job continues that trace, so an approval round trip reads as one trace.

### Session grouping, and why no per-backend adapters

Every span in a job carries the conversation id as `gen_ai.conversation.id` and as `session.id`, plus `dash.job.id` and `dash.job.kind`. Both backends read that without translation:

- Langfuse reads a session from `langfuse.session.id` or `session.id` ([Langfuse OpenTelemetry docs](https://langfuse.com/integrations/native/opentelemetry)) and maps `gen_ai.*` attributes onto its data model.
- Phoenix treats OpenInference as native and lists `session.id` among its common attributes. From arize-phoenix 15.10.0 it converts `gen_ai.*` spans to OpenInference on arrival, keeping the originals and filling only gaps ([Phoenix release notes, 2026-05-15](https://arize.com/docs/phoenix/release-notes/05-2026/05-15-2026-otel-semconv-conversion)).
- Pydantic AI already emits `gen_ai.conversation.id` on the run span, but dash builds its `Conversation` without an id, so the value would be Pydantic AI's own. Seeding `Conversation.conversation_id` with dash's conversation id makes it the same value everywhere. `session.id` is added by a span processor that copies it from the baggage Pydantic AI sets.

So dash exports one set of attributes. If a backend version lags, the collector's `transform` processor can copy or rename an attribute; that is configuration in the collector, not code in dash. Minimum versions to run: Langfuse 3.22 (self-hosted OTLP) and Phoenix 15.10.

### Trace context through the queue

The API puts a W3C `traceparent` in the job payload when it queues one. The worker starts its job span as a child, so the request and the work are one trace. Jobs queued with no context start a new trace.

### Content capture is a governance switch

Prompts and completions hold personal data and tool output. `TELEMETRY_CAPTURE_CONTENT` defaults to off, so a default install exports timing, models, token counts, tool names and outcomes only. Tool arguments are content: a `run_command` command line is captured only when the flag is on. The sandbox GitHub token is already masked in output; the masking runs before anything is recorded.

## Risks

- A slow or down collector must not slow or fail a turn. The batch processor exports off the request path and drops spans when its queue is full.
- Content capture on a shared backend puts conversation text in a second store. The flag is per deployment and the spec requires it off by default.
- Attribute conventions for `gen_ai.*` are still moving. `InstrumentationSettings` takes a `version` (2 to 6) for the convention it emits. Pin it, and check the backend mapping when bumping Pydantic AI.

## Open Questions

- Do token counts and costs show in each backend from `gen_ai.usage.*` alone? Check on a running Phoenix and Langfuse before the collector config lands; a `transform` rule is the fallback.
- Should dash also export metrics (queue depth, job duration)? Out of scope here; traces first.
