# chat Specification

## Purpose

Talk to dash's agent in saved conversations. A message becomes a job on a Redis queue, and a worker runs an agent turn and streams it into a per-job event stream, which the browser follows over server-sent events. The worker keeps each conversation's turn history, and a turn can stop to wait for a person's approval and resume later. The same queue also carries `update` jobs from `dash scrape`, covered by the `sources` spec.

## Requirements

### Requirement: Conversations are saved and listed by recent activity

The system SHALL store conversations and their messages. The conversation list SHALL return at most 50 conversations, most recently active first.

#### Scenario: Create a conversation

- **WHEN** a client creates a conversation
- **THEN** the response is 201 with the conversation's `id` and the title `New conversation`

#### Scenario: Activity moves a conversation to the top

- **WHEN** a message is added to an older conversation
- **THEN** that conversation is listed before conversations with no newer activity

### Requirement: Conversations can be deleted and their messages read

The system SHALL delete a conversation and its messages by id and return 204, or 404 if there is none. It SHALL list a conversation's messages in order, each with its `id`, `role`, `content` and the `events` its reply was shown with.

#### Scenario: Unknown conversation

- **WHEN** a client deletes a conversation id that does not exist
- **THEN** the response is 404

#### Scenario: Messages carry their events

- **WHEN** a client lists the messages of a conversation with a streamed reply
- **THEN** the assistant message includes the events shown while it streamed

### Requirement: The first message names the conversation

The system SHALL title a conversation still named `New conversation` after the first line of the first user message, cut to 80 characters.

#### Scenario: First user message

- **WHEN** a user message is added to a conversation titled `New conversation`
- **THEN** the title becomes the first line of that message, at most 80 characters

#### Scenario: Later messages leave the title alone

- **WHEN** a user message is added to a conversation that already has a title
- **THEN** the title does not change

### Requirement: Sending a message queues a reply job

The system SHALL accept a user message for an existing conversation, store it, add a job to the queue, and return 202 with the `job_id`. A message SHALL have between 1 and 100,000 characters.

#### Scenario: Message accepted

- **WHEN** a client posts a valid message to an existing conversation
- **THEN** the message is stored with role `user`, one job is queued for that conversation, and the response is 202 with a `job_id`

#### Scenario: Unknown conversation

- **WHEN** a client posts a message to a conversation that does not exist
- **THEN** the response is 404 and nothing is stored or queued

#### Scenario: Empty or oversized message

- **WHEN** a client posts a message that is empty or longer than 100,000 characters
- **THEN** the request is rejected and nothing is stored or queued

### Requirement: Replies stream as job events

The worker SHALL append `delta` (reply text), `reasoning` (the model's thinking, where it gives any), `memories` (the recalled text), `tool` (tool progress), `status` (a `message` about the turn) and `approval` (a call waiting for a person) events to the job's own stream. It SHALL batch text so each event holds at least 48 characters, except the last of a run. After the reply is stored as an `assistant` message, it SHALL append a `done` event carrying the `message_id`.

#### Scenario: Successful reply

- **WHEN** the agent streams a reply
- **THEN** the job's events include the `delta` events that spell out the reply exactly once, then `done`, and the full reply is stored as one assistant message with its events

#### Scenario: Memories event

- **WHEN** at least one memory was recalled for the job
- **THEN** a `memories` event listing their text comes before the first `delta`

#### Scenario: A reply waits for approval

- **WHEN** the agent calls a tool set to `ask`
- **THEN** an `approval` event for that call comes before `done`, and `done` lists its item in `awaiting`

### Requirement: A job's events can be followed and replayed

The system SHALL serve a job's events as server-sent events at `/api/jobs/{job_id}/events`. A client SHALL receive every event from the start of the job, whenever it connects, then new events as they arrive, until a `done` or `error` event. While idle the stream SHALL send a comment line (`: ping`) at least every 15 seconds. The system SHALL keep a job's events for one hour after the last event, and SHALL stop streaming when the client disconnects.

#### Scenario: Connect after the reply started

- **WHEN** a client opens the events stream after some `delta` events exist
- **THEN** it receives those events first, then the rest, and the stream ends after `done`

#### Scenario: Malformed job id

- **WHEN** a client requests events for a job id that is not alphanumeric
- **THEN** the response is 400

### Requirement: Jobs survive worker failure

The queue SHALL give each job to one worker at a time and remove it only after the worker finishes it, with a reply or an error. A job held unfinished for five minutes SHALL be given to another worker. A worker that cannot reach the queue SHALL keep running and retry every two seconds.

#### Scenario: Worker dies mid-job

- **WHEN** a worker takes a job and stops without finishing it
- **THEN** after five minutes another worker takes the job

#### Scenario: Queue outage

- **WHEN** the queue is unreachable and then recovers
- **THEN** the worker resumes taking jobs without being restarted

### Requirement: Queue status

The system SHALL report the number of waiting jobs, jobs in flight, and workers at `/api/queue`.

#### Scenario: One job running

- **WHEN** one worker holds one job and none are waiting
- **THEN** the report shows `in_flight` 1, `waiting` 0 and `workers` 1

### Requirement: Every job is recorded on a live timeline

Before handling a job, the worker SHALL record it with its job id, its kind (`chat`, `update` or `resume`) and its data: a chat job's conversation id, an update job's item, a resume job's conversation id and approval item ids. The system SHALL list the newest 100 entries, newest first, at `/api/live`, each with its `id`, `kind`, `data` and creation time.

#### Scenario: A chat job appears

- **WHEN** the worker picks up a chat job
- **THEN** `/api/live` lists an entry of kind `chat` with that conversation's id

#### Scenario: A resume job appears

- **WHEN** the worker picks up a resume job
- **THEN** `/api/live` lists an entry of kind `resume` with the conversation id and the answered item ids

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

The worker SHALL end a turn that would make more model requests than `AGENT_REQUEST_LIMIT` (default 30), or more tool calls than `AGENT_TOOL_CALL_LIMIT` (default 50). The job ends with an `error` event beginning `agent:` that names the limit.

#### Scenario: A runaway tool loop

- **WHEN** the agent keeps calling tools past `AGENT_TOOL_CALL_LIMIT`
- **THEN** the job ends with an `error` event naming the tool call limit, and the turn history is unchanged

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

A `tool` event SHALL carry `tool`, `toolCallId` and `status`. A starting call has `status` `running` and a `label` of at most 120 characters from its arguments. A finished call has `status` `completed`, `failed` (it reported an error back to the model), `interrupted` (the turn was stopped first) or `denied` (a person denied it, or it was superseded or expired). A call waiting for approval has no finishing event until it is answered.

#### Scenario: A tool call

- **WHEN** the agent calls a tool with the argument `{"command": "git status"}` during a reply
- **THEN** a `tool` event with `status` `running` and `label` `git status` comes before a `tool` event with the same `toolCallId` and `status` `completed`

#### Scenario: A tool fails

- **WHEN** a tool reports an error back to the model
- **THEN** its finishing `tool` event has `status` `failed`, and the turn continues

#### Scenario: A denied call

- **WHEN** a person denies a waiting call and the turn resumes
- **THEN** the resumed job has a `tool` event for that call with `status` `denied`, and the call does not run

### Requirement: A stored reply keeps its events

The worker SHALL store, with each assistant message, the events shown while it streamed, in order, so a reload can rebuild the reply as it was shown.

#### Scenario: Reload mid-conversation

- **WHEN** a client reloads a conversation whose reply called a tool
- **THEN** the stored message's events include that tool's `running` and `completed` events, in the order they streamed
