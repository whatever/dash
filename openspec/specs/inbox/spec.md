# inbox Specification

## Purpose

Things the agent leaves for the person: approvals it is waiting on, and messages that need no answer. Answering every approval from a turn resumes that turn, "allow always" saves a rule for that exact call, and approvals expire after 24 hours.

## Requirements

### Requirement: Inbox items can be listed and counted

The system SHALL keep inbox items, each with an `id`, a `kind` (`approval` or `message`), a `status` (`open`, `resolved`, `dismissed` or `expired`), a `title`, a `body`, a `data` object, the `conversation_id` it came from, and its creation and resolution times.
- `GET /api/inbox` SHALL list at most 100 items, newest first. It lists `open` items unless `status=all` is given.
- `GET /api/inbox/count` SHALL return the number of open items as `{"open": <n>}`.

#### Scenario: Open items only

- **WHEN** there is one open approval and one dismissed message
- **THEN** `/api/inbox` lists only the approval, and `/api/inbox/count` returns `{"open": 1}`

#### Scenario: Everything

- **WHEN** a client requests `/api/inbox?status=all`
- **THEN** both items are listed, newest first

### Requirement: A tool set to ask waits for approval

When the model calls a tool that `AGENT_TOOL_POLICY` sets to `ask`, and no saved rule matches the call, the tool SHALL NOT run. The system SHALL open one `approval` item per such call. Its `data` SHALL hold the tool, its arguments and a label of at most 120 characters.

#### Scenario: A command needs approval

- **WHEN** `run_command` is set to `ask` and the model calls it with `git push`
- **THEN** no command runs, and an open approval item for `run_command` with `git push` exists

### Requirement: A turn waiting for approval ends with approval events

A turn with calls waiting for approval SHALL end with one `approval` event per call, carrying the `item_id`, the `tool`, the `label` and the call's `toolCallId`. The worker SHALL store the reply text so far as an assistant message, and SHALL end the job with a `done` event carrying the `message_id` and `awaiting`, the list of waiting item ids.

#### Scenario: The job ends waiting

- **WHEN** a turn opens an approval for `git push`
- **THEN** the job ends with an `approval` event for that item, then `done` listing it in `awaiting`

### Requirement: Approvals can be answered

The system SHALL accept `POST /api/inbox/{id}/resolve` with a `decision` of `allow`, `allow_always` or `deny`, and SHALL mark the approval `resolved` with that decision. It SHALL return 404 for an unknown item, and 409 for an item that is not an open approval.

#### Scenario: Answered twice

- **WHEN** a client resolves an approval that is already resolved
- **THEN** the response is 409 and nothing is queued

#### Scenario: Unknown item

- **WHEN** a client resolves an item id that does not exist
- **THEN** the response is 404

### Requirement: Answering every approval from a turn resumes it

When no approval from the same turn is left open, the system SHALL queue a `resume` job for the conversation, and the answer SHALL return 202 with its `job_id`. While any approval from that turn is still open, the answer SHALL return 202 without one. The `resume` job SHALL run the allowed calls, tell the model which were denied, and stream the reply as a new assistant message, with the same events as a chat reply.

#### Scenario: Allowed

- **WHEN** the only open approval from a turn is resolved with `allow`
- **THEN** a `resume` job runs the call, and its reply streams and is stored as a new assistant message

#### Scenario: Denied

- **WHEN** the approval is resolved with `deny`
- **THEN** the call does not run, and the resumed reply is generated knowing the call was denied

#### Scenario: Two approvals from one turn

- **WHEN** a turn opened two approvals and only one is resolved
- **THEN** no `resume` job is queued until the second is resolved

### Requirement: Allow always saves a rule for that exact call

Resolving an approval with `allow_always` SHALL save a rule for that tool with those exact arguments. A later call to the same tool with identical arguments SHALL run without asking. A call with any other arguments SHALL still ask. The system SHALL list saved rules at `GET /api/inbox/rules` and delete one with `DELETE /api/inbox/rules/{id}`.

#### Scenario: The same command again

- **WHEN** `git status` was allowed always and the model later calls `run_command` with `git status`
- **THEN** the command runs without an approval

#### Scenario: A different command

- **WHEN** the model calls `run_command` with `git push`
- **THEN** it still needs approval

### Requirement: A new message supersedes open approvals

When a user message is sent to a conversation that has open approvals, the system SHALL resolve those approvals as denied with the reason `superseded`. It SHALL answer the new message in a turn whose model request also reports those calls as denied.

#### Scenario: Writing instead of answering

- **WHEN** a turn is waiting on an approval and the user sends a new message
- **THEN** the approval becomes `resolved` with `superseded`, and the reply to the new message is generated knowing the call was denied

### Requirement: Approvals expire after 24 hours

The system SHALL mark an approval still open 24 hours after it was created as `expired`. An expired call SHALL be reported to the model as denied on the conversation's next turn. An expired approval SHALL NOT be resumed on its own.

#### Scenario: An old approval

- **WHEN** an approval has been open for more than 24 hours
- **THEN** its status is `expired`, and resolving it returns 409

### Requirement: The agent can leave a message

The agent SHALL have a `leave_message` tool that opens a `message` item with a title of at most 120 characters, a body of at most 4,000 characters, and at most 10 source URLs, linked to the conversation it came from. The tool SHALL return the new item's id, and it follows the tool policy like any other tool.

#### Scenario: A note for later

- **WHEN** the agent calls `leave_message` with a title, a body and one source URL
- **THEN** an open `message` item with that title, body and source exists, and `/api/inbox/count` goes up by one

### Requirement: Messages can be dismissed

The system SHALL accept `POST /api/inbox/{id}/dismiss` for an open message, mark it `dismissed` and return 204. It SHALL return 409 for an approval or an item that is not open, and 404 for an unknown item.

#### Scenario: Dismiss a message

- **WHEN** a client dismisses an open message
- **THEN** it is no longer listed as open, and the response is 204

#### Scenario: Dismissing an approval

- **WHEN** a client dismisses an open approval
- **THEN** the response is 409, and the approval stays open
