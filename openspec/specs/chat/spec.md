# chat Specification

## Purpose

Talk to the hermes agent in saved conversations. A message becomes a job on a Redis queue, a worker streams hermes's reply into a per-job event stream, and the browser follows that stream over server-sent events. The same queue also carries `update` jobs from `dash scrape`, covered by the `sources` spec.

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

### Requirement: Replies come from hermes

The worker SHALL answer a job by streaming a response from the hermes router's `/responses` endpoint, using the model named by `HERMES_MODEL`. The request SHALL name the conversation `dash:<conversation id>` and carry only the newest user message as its input, because hermes holds the earlier turns under that name. When memories were recalled, the request SHALL carry them as `instructions`. The worker SHALL send a bearer token only when `HERMES_API_KEY` is set.

#### Scenario: Only the new message is sent

- **WHEN** a conversation has earlier messages and the user sends another
- **THEN** hermes receives the new message under the conversation name `dash:<conversation id>`, not the stored history

#### Scenario: Recalled memories ride as instructions

- **WHEN** memories were recalled for the job
- **THEN** the request carries them as `instructions`

#### Scenario: Nothing recalled

- **WHEN** no memories were recalled
- **THEN** the request carries no `instructions`

#### Scenario: No API key

- **WHEN** `HERMES_API_KEY` is empty
- **THEN** requests to hermes carry no `Authorization` header

### Requirement: Replies stream as job events

The worker SHALL append events to the job's own stream: `delta` (reply text), `reasoning`, `memories` (the recalled text), and `tool` and `status` (hermes's progress). It SHALL batch text so each event holds at least 48 characters, except the last of a run. After the reply is stored as an `assistant` message, it SHALL append a `done` event carrying the `message_id`. The stored message SHALL keep the events shown, in order, so a reload can rebuild the reply.

#### Scenario: Successful reply

- **WHEN** hermes streams a reply
- **THEN** the job's events include the `delta` events that spell out the reply, then `done`, and the full reply is stored as one assistant message with its events

#### Scenario: Memories event

- **WHEN** at least one memory was recalled for the job
- **THEN** a `memories` event listing their text comes before the first `delta`

### Requirement: Failures end the job with an error event

The worker SHALL end a job that cannot be answered with a single `error` event carrying a message, and SHALL NOT store an assistant message for it.

#### Scenario: hermes fails

- **WHEN** the call to hermes raises an error part-way through
- **THEN** the job ends with an `error` event beginning `hermes:`, no assistant message is stored, and no memories are extracted

#### Scenario: Nothing to answer

- **WHEN** a job's conversation is empty or its last message is not from the user
- **THEN** the job ends with the `error` event `No user message to answer.`

#### Scenario: Unexpected failure

- **WHEN** handling a job raises an unexpected error
- **THEN** the job ends with an `error` event and is acknowledged, so it is not retried

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

Before handling a job, the worker SHALL record it with its job id, its kind (`chat` or `update`) and its data: a chat job's conversation id, an update job's item. The system SHALL list the newest 100 entries, newest first, at `/api/live`, each with its `id`, `kind`, `data` and creation time.

#### Scenario: A chat job appears

- **WHEN** the worker picks up a chat job
- **THEN** `/api/live` lists an entry of kind `chat` with that conversation's id
