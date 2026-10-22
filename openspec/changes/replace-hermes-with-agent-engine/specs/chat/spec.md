## REMOVED Requirements

### Requirement: Replies come from hermes

**Reason**: hermes-agent is replaced by an agent that runs inside the worker.

**Migration**: Set `AGENT_MODEL`, plus `AGENT_BASE_URL` and `AGENT_API_KEY` for an OpenAI-compatible API, in place of `HERMES_BASE_URL`, `HERMES_API_KEY` and `HERMES_MODEL`. Remove the hermes deployment and the `dash-hermes` secret.

### Requirement: Failures end the job with an error event

**Reason**: Its "hermes fails" scenario describes the removed hermes call. The requirement is restated, with a scenario for the agent, as "A failed job ends with an error event".

**Migration**: None. Clients see the same single `error` event, now beginning `agent:` instead of `hermes:`.

## ADDED Requirements

### Requirement: Replies come from the agent

The worker SHALL answer a job by running its agent on the model named by `AGENT_MODEL`. The agent receives the conversation's turn history and the newest user message. When `AGENT_BASE_URL` is set, the worker SHALL send model requests to that OpenAI-compatible API, with `AGENT_API_KEY` as the bearer token when it is set. When memories were recalled, the agent SHALL receive them as instructions for that turn only.

#### Scenario: The history goes with the message

- **WHEN** a conversation has earlier turns and the user sends another message
- **THEN** the model receives the earlier turns, including their tool calls and results, followed by the new message

#### Scenario: Recalled memories ride as instructions

- **WHEN** memories were recalled for the job
- **THEN** the model request carries them as instructions, and later turns do not repeat them unless they are recalled again

#### Scenario: OpenAI-compatible API

- **WHEN** `AGENT_BASE_URL` is set
- **THEN** model requests go to that URL, naming the model `AGENT_MODEL`

### Requirement: The turn history is kept per conversation

The worker SHALL store each conversation's turn history, with every model message, tool call and tool result, when a turn ends. A turn that fails SHALL leave the stored history as it was before the turn. Deleting a conversation SHALL delete its history. A conversation with no stored history SHALL start from its stored user and assistant messages.

#### Scenario: A failed turn leaves no trace

- **WHEN** a turn fails part-way and the user then sends another message
- **THEN** the model receives the history from before the failed turn, and the new turn can succeed

#### Scenario: A conversation from before the upgrade

- **WHEN** a conversation has stored messages but no stored history
- **THEN** its next turn starts with those user and assistant messages as text

### Requirement: A running turn can be stopped

The system SHALL accept `POST /api/jobs/{job_id}/stop` for a job id and return 202. When the worker sees the request, it SHALL stop the turn within 2 seconds. It SHALL store the reply text streamed so far as an assistant message, store the history the stopped run returns, and end the job with a `done` event carrying the `message_id` and `stopped` true.

#### Scenario: Stop mid-reply

- **WHEN** a client asks to stop a job while its reply is streaming
- **THEN** the job ends with `done` and `stopped` true, the partial reply is stored, and the next message in the conversation is answered normally

#### Scenario: Malformed job id

- **WHEN** a client asks to stop a job id that is not alphanumeric
- **THEN** the response is 400

### Requirement: Every turn has a budget

The worker SHALL give each turn its own budget. A turn SHALL end when it would make more model requests than `AGENT_REQUEST_LIMIT` (default 60), or more tool calls than `AGENT_TOOL_CALL_LIMIT` (default 100). Requests and tool calls made in earlier turns of the conversation SHALL NOT count against it. The job ends with an `error` event beginning `agent:` that says the turn hit the limit and names it.

#### Scenario: A runaway tool loop

- **WHEN** the agent keeps calling tools past `AGENT_TOOL_CALL_LIMIT`
- **THEN** the job ends with an `error` event naming the tool call limit, and the turn history is unchanged

#### Scenario: A long conversation

- **WHEN** a conversation has used more than `AGENT_REQUEST_LIMIT` model requests across many turns, each within the limit
- **THEN** the next turn runs normally

### Requirement: A failed job ends with an error event

The worker SHALL end a job that cannot be answered with a single `error` event carrying a message, and SHALL NOT store an assistant message for it.

#### Scenario: The agent fails

- **WHEN** a model request raises an error part-way through
- **THEN** the job ends with an `error` event beginning `agent:`, no assistant message is stored, no memories are extracted, and the turn history is unchanged

#### Scenario: Nothing to answer

- **WHEN** a job's conversation is empty or its last message is not from the user
- **THEN** the job ends with the `error` event `No user message to answer.`

#### Scenario: Unexpected failure

- **WHEN** handling a job raises an unexpected error
- **THEN** the job ends with an `error` event and is acknowledged, so it is not retried

### Requirement: Tool calls show as tool events

A `tool` event SHALL carry `tool`, `toolCallId` and `status`. A starting call has `status` `running` and a `label` of at most 120 characters from its arguments. A finished call has `status` `completed`, `failed` (it reported an error back to the model) or `interrupted` (the turn was stopped first).

#### Scenario: A tool call

- **WHEN** the agent calls a tool with the argument `{"command": "git status"}` during a reply
- **THEN** a `tool` event with `status` `running` and `label` `git status` comes before a `tool` event with the same `toolCallId` and `status` `completed`

#### Scenario: A tool fails

- **WHEN** a tool reports an error back to the model
- **THEN** its finishing `tool` event has `status` `failed`, and the turn continues

### Requirement: A stored reply keeps its events

The worker SHALL store, with each assistant message, the events shown while it streamed, in order, so a reload can rebuild the reply as it was shown.

#### Scenario: Reload mid-conversation

- **WHEN** a client reloads a conversation whose reply called a tool
- **THEN** the stored message's events include that tool's `running` and `completed` events, in the order they streamed

## MODIFIED Requirements

### Requirement: Replies stream as job events

The worker SHALL append `delta` (reply text), `reasoning` (the model's thinking, where it gives any), `memories` (the recalled text), `tool` (tool progress) and `status` (a `message` about the turn) events to the job's own stream. It SHALL batch text so each event holds at least 48 characters, except the last of a run. After the reply is stored as an `assistant` message, it SHALL append a `done` event carrying the `message_id`.

#### Scenario: Successful reply

- **WHEN** the agent streams a reply
- **THEN** the job's events include the `delta` events that spell out the reply exactly once, then `done`, and the full reply is stored as one assistant message with its events

#### Scenario: Memories event

- **WHEN** at least one memory was recalled for the job
- **THEN** a `memories` event listing their text comes before the first `delta`
