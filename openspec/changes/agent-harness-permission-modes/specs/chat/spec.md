## ADDED Requirements

### Requirement: Each conversation has a permission mode

The system SHALL store each conversation's `permission_mode` as `manual`, `auto`, or `plan` (default `auto`). The `POST /api/conversations` endpoint SHALL accept `permission_mode` in the body. The `PATCH /api/conversations/{id}` endpoint SHALL update the mode. Changing the mode SHALL NOT affect jobs already in flight.

#### Scenario: Create a conversation in manual mode

- **WHEN** a client creates a conversation with `permission_mode: manual`
- **THEN** the conversation is stored with that mode

#### Scenario: Change the permission mode

- **WHEN** a client patches a conversation to set `permission_mode: auto`
- **THEN** the conversation is updated, and future jobs use the new mode

#### Scenario: Default mode is auto

- **WHEN** a client creates a conversation without specifying `permission_mode`
- **THEN** the conversation is stored with `permission_mode: auto`

### Requirement: Manual mode queues tool calls for approval

When the conversation's `permission_mode` is `manual`, the worker SHALL:
1. Emit a `tool` event with `status: awaiting_approval` when a tool call is requested.
2. Record the tool call in the approval queue.
3. Poll the approval queue with a timeout of `AGENT_MANUAL_APPROVAL_TIMEOUT` (default 120 seconds).
4. If approved before timeout, emit a `tool` event with `status: approved` and run the tool.
5. If denied before timeout, end the turn with an `error` event.
6. If timeout expires, treat it as a denial and end the turn.

#### Scenario: A tool call awaits approval

- **WHEN** the agent calls a tool in a conversation with `permission_mode: manual`
- **THEN** a `tool` event with `status: awaiting_approval` appears in the stream, and the worker waits for a decision

#### Scenario: Tool call is approved

- **WHEN** a client posts to `/api/approvals/{job_id}/{toolCallId}` before the timeout
- **THEN** a `tool` event with `status: approved` is emitted, the tool runs, and the job continues

#### Scenario: Tool call is denied

- **WHEN** a client posts to `DELETE /api/approvals/{job_id}/{toolCallId}` before the timeout
- **THEN** an `error` event ends the job with a message like `Tool call denied: git_command`

#### Scenario: Tool call approval times out

- **WHEN** no decision arrives before `AGENT_MANUAL_APPROVAL_TIMEOUT` expires
- **THEN** the job ends with an `error` event like `Tool approval timed out: git_command after 120s`

### Requirement: Auto mode follows the tool policy

When the conversation's `permission_mode` is `auto`, the worker SHALL apply `AGENT_TOOL_POLICY` to each tool call. Tools set to `ask` SHALL be hidden from the agent, as if they were set to `never`. No approval queue is used.

#### Scenario: Auto mode tools follow policy

- **WHEN** the agent calls a tool in a conversation with `permission_mode: auto` and `AGENT_TOOL_POLICY` sets it to `auto`
- **THEN** the tool runs immediately without an approval step

#### Scenario: Auto mode hides ask tools

- **WHEN** a tool is set to `ask` in `AGENT_TOOL_POLICY` and the conversation is in `permission_mode: auto`
- **THEN** the tool is hidden from the model and cannot be called

### Requirement: Plan mode is a placeholder

When the conversation's `permission_mode` is `plan`, the worker SHALL behave as if it were `manual` for now. A future change will implement the full plan mode.

#### Scenario: Plan mode acts like manual

- **WHEN** a conversation is in `permission_mode: plan`
- **THEN** tool calls queue for approval as in manual mode

## MODIFIED Requirements

### Requirement: Sending a message queues a reply job

The worker SHALL accept a user message for an existing conversation with a valid `permission_mode`, store it, add a job to the queue, and return 202 with the `job_id`. The job's handling SHALL respect the conversation's permission mode.

#### Scenario: Message includes permission mode

- **WHEN** a client posts a message to a conversation with `permission_mode: manual`
- **THEN** the job's tool calls are queued for approval
