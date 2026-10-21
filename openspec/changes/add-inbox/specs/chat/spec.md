## MODIFIED Requirements

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

### Requirement: Every job is recorded on a live timeline

Before handling a job, the worker SHALL record it with its job id, its kind (`chat`, `update` or `resume`) and its data: a chat job's conversation id, an update job's item, a resume job's conversation id and approval item ids. The system SHALL list the newest 100 entries, newest first, at `/api/live`, each with its `id`, `kind`, `data` and creation time.

#### Scenario: A chat job appears

- **WHEN** the worker picks up a chat job
- **THEN** `/api/live` lists an entry of kind `chat` with that conversation's id

#### Scenario: A resume job appears

- **WHEN** the worker picks up a resume job
- **THEN** `/api/live` lists an entry of kind `resume` with the conversation id and the answered item ids
