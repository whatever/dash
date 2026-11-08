# telemetry Specification

## Purpose

Traces of what dash does, exported over OpenTelemetry, so an operator can see each model call and tool call, group them by conversation, and send them to a backend of their choice.

## ADDED Requirements

### Requirement: Export is off unless an endpoint is set

The system SHALL export traces over OTLP only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set, and SHALL read the standard `OTEL_EXPORTER_OTLP_*` variables for headers, protocol and timeout. When it is unset, the system SHALL export nothing and SHALL behave exactly as it does without telemetry.

#### Scenario: No endpoint

- **WHEN** the API and worker start with `OTEL_EXPORTER_OTLP_ENDPOINT` unset
- **THEN** no trace data leaves the process and replies are unchanged

#### Scenario: Endpoint set

- **WHEN** the endpoint is set and a person sends a chat message
- **THEN** the endpoint receives spans for that job

### Requirement: Each process reports under its own service name

The system SHALL report spans from the API as `dash-api`, from the worker as `dash-worker` and from `dash scrape` as `dash-scrape`, unless `OTEL_SERVICE_NAME` overrides it.

#### Scenario: Default names

- **WHEN** the API, worker and scrape command run with an endpoint set
- **THEN** their spans carry service names `dash-api`, `dash-worker` and `dash-scrape`

### Requirement: Every model call is traced

The system SHALL record a span for each chat turn, each tool call in a turn, each embedding request, each memory fact extraction and each fact extraction from a source update. A span SHALL carry the model name, how long the call took and its outcome. It SHALL carry input and output token counts when the provider reports them.

#### Scenario: A turn with a tool call

- **WHEN** a chat turn calls one tool
- **THEN** the trace has a turn span with a child span for that tool call

#### Scenario: Memory work

- **WHEN** a reply is saved and the worker embeds the message and extracts facts
- **THEN** the same trace has a span for the embedding and a span for the extraction

#### Scenario: A call fails

- **WHEN** a model call raises an error
- **THEN** its span is marked as an error with the error type, and the job proceeds as it does without telemetry

### Requirement: Spans are grouped by conversation

The system SHALL attach the conversation's id to every span of a job as `gen_ai.conversation.id` and `session.id`, and SHALL attach the job's id and kind as `dash.job.id` and `dash.job.kind`. A job that belongs to no conversation SHALL carry the job attributes only.

#### Scenario: Two jobs in one chat

- **WHEN** a person sends two messages in one conversation
- **THEN** the spans of both jobs carry the same `session.id`

### Requirement: A job continues the trace of the request that queued it

The system SHALL pass the W3C trace context from a request into the job it queues, and the worker SHALL continue that trace. A resumed job after an approval SHALL continue the trace of the turn that asked.

#### Scenario: Request to worker

- **WHEN** a client posts a chat message and the worker answers it
- **THEN** the API's span and the worker's spans share one trace id

#### Scenario: Approval resume

- **WHEN** a person answers an approval and the turn resumes
- **THEN** the resumed spans share the trace id of the turn that asked for approval

### Requirement: Content is not exported unless the operator allows it

The system SHALL leave out prompt text, completion text, tool arguments, tool results and memory text from every span unless `TELEMETRY_CAPTURE_CONTENT` is `true`. It SHALL still record model names, token counts, durations, tool names and outcomes. The default SHALL be off.

#### Scenario: Default

- **WHEN** a chat turn runs a command with the setting unset
- **THEN** its spans name the tool and the outcome and hold neither the command line nor the reply text

#### Scenario: Capture on

- **WHEN** `TELEMETRY_CAPTURE_CONTENT` is `true`
- **THEN** the spans hold the prompt, the reply and the tool arguments, with secrets masked as they are for the model

### Requirement: An unreachable collector does not affect replies

The system SHALL export spans off the path that answers a person. When the endpoint is slow or down, replies SHALL keep their speed and content, spans MAY be dropped, and the failure SHALL be logged without failing a job.

#### Scenario: Endpoint down

- **WHEN** the endpoint refuses connections during a chat
- **THEN** the reply streams and is saved as usual and a warning is logged

### Requirement: The stack ships a collector

The compose stack and the chart SHALL include an OpenTelemetry Collector that accepts OTLP from dash and can forward to other backends by configuration alone. The chart SHALL add nothing when telemetry is not enabled.

#### Scenario: Compose

- **WHEN** an operator starts the compose stack and sends a chat
- **THEN** the collector receives the job's spans

#### Scenario: Chart defaults

- **WHEN** the chart is rendered with default values
- **THEN** it has no collector and sets no `OTEL_*` variables
