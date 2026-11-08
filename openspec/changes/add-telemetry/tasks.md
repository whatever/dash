## 1. Telemetry module

- [ ] 1.1 Add a module that, when `OTEL_EXPORTER_OTLP_ENDPOINT` is set, installs a tracer provider with a batch OTLP/HTTP exporter and the service names `dash-api`, `dash-worker` and `dash-scrape`. Verify: unit test that unset means no provider, and that an in-memory exporter sees a span when set.
- [ ] 1.2 Start it from the API, the worker and `dash scrape`. Verify: each process exports spans under its own service name.
- [ ] 1.3 Add `TELEMETRY_CAPTURE_CONTENT` (default off). Verify: unit test that prompt, completion and tool arguments are absent by default and present when on.

## 2. Spans

- [ ] 2.1 Put the conversation id, job id and job kind on every span of a job. Verify: test reads the attributes from an in-memory exporter.
- [ ] 2.2 Span chat turns and tool calls (Pydantic AI instrumentation on the agent engine, one manual span on hermes). Verify: a turn with a tool call yields a turn span with a child tool span.
- [ ] 2.3 Span embeddings, memory fact extraction and source-update extraction with model name and token usage. Verify: a failing extractor yields an error span and the job still finishes.
- [ ] 2.4 Carry `traceparent` in the queued job and the inbox row. Verify: a request, its job and an approval resume share one trace id.

## 3. Collector

- [ ] 3.1 Add an `otel-collector` service to compose that receives OTLP and logs spans, with a file for adding exporters. Verify: `docker compose up`, send a chat, see spans in the collector log.
- [ ] 3.2 Add `telemetry.endpoint` and `telemetry.captureContent` to the chart and an optional collector Deployment. Verify: `helm template` with the values unset renders nothing new.
- [ ] 3.3 Run Phoenix and Langfuse behind the collector in the cluster and check session grouping and token counts in each (operator repo, not this one).
