## ADDED Requirements

### Requirement: A routine is a prompt on a schedule

The system SHALL store routines with a `name` of 1 to 120 characters, a `prompt` of 1 to 8,000 characters, a schedule, a `timezone`, an `owner` of `user` or `agent`, `enabled`, `notify` and `labels`. The schedule SHALL be either a five-field `cron` expression or a single `run_at` time, never both. `timezone` SHALL be an IANA zone name and default to the deployment's setting. `labels` SHALL be a JSON object that is stored and returned and has no other effect.

#### Scenario: A recurring routine

- **WHEN** a client creates a routine with cron `0 8 * * 1-5` and zone `America/New_York`
- **THEN** it is stored enabled, with its next run at the next 8:00 on a weekday in that zone

#### Scenario: Both schedules or neither

- **WHEN** a client creates a routine with both `cron` and `run_at`, or with neither
- **THEN** the request is rejected and nothing is stored

#### Scenario: A bad expression or zone

- **WHEN** a client creates a routine with a cron expression that does not parse, or a zone that does not exist
- **THEN** the request is rejected and nothing is stored

### Requirement: Routines can be managed over HTTP

The system SHALL let a client list, create, change and delete routines, and run one at once. Each listed routine SHALL carry its `id`, schedule, `timezone`, `owner`, `enabled`, `next_run_at`, `last_run_at` and `expires_at`. Changing or deleting a routine that is not stored SHALL return 404.

#### Scenario: Pause

- **WHEN** a client sets `enabled` to false on a routine
- **THEN** it is listed as not enabled, has no next run and does not fire

#### Scenario: Run now

- **WHEN** a client runs a routine at once
- **THEN** a run starts as for a scheduled fire, and the routine's schedule is unchanged

#### Scenario: Unknown routine

- **WHEN** a client changes or deletes an id that is not stored
- **THEN** the response is 404

### Requirement: A due routine fires once

When a routine's next run time has passed, the system SHALL start exactly one run for that time, however many workers are running, and SHALL then move the routine to its next run time. For a `run_at` routine the system SHALL then disable it. A run SHALL start within two minutes of its time while a worker is running.

#### Scenario: Two workers

- **WHEN** two workers are running and a routine becomes due
- **THEN** one run starts

#### Scenario: A repeated fire

- **WHEN** the same fire for the same routine and time is enqueued twice, such as after a worker restart
- **THEN** one run happens

#### Scenario: A one-time routine

- **WHEN** a `run_at` routine fires
- **THEN** it is disabled and does not fire again

### Requirement: A missed run fires once

When a routine was due several times while no worker was running, the system SHALL start one run when a worker returns, and SHALL compute the next run time from that moment. When a routine's previous run is still in progress at its next fire time, that fire SHALL be skipped and the routine SHALL move to its following run time.

#### Scenario: Worker down

- **WHEN** an hourly routine was due 5 times while the worker was down
- **THEN** one run starts when the worker returns and the next is an hour later

#### Scenario: A slow run

- **WHEN** a routine is due while its previous run has not finished
- **THEN** no second run starts

### Requirement: Each run is a new conversation

A run SHALL start a new conversation titled with the routine's name and the time, containing the routine's prompt as the user's message, answered by the agent as in any chat. The conversation SHALL record the routine that started it. The run SHALL appear on the Live timeline.

#### Scenario: Reading a run

- **WHEN** a routine fires
- **THEN** a new conversation exists with the prompt and the agent's reply, and it names the routine that started it

#### Scenario: Two runs

- **WHEN** a routine fires on two days
- **THEN** there are two separate conversations, and the second does not see the first's messages

### Requirement: A run reports to the inbox

When a run finishes and `notify` is true, the system SHALL leave an inbox message titled with the routine's name that holds the agent's final reply. When a run fails, the system SHALL leave an inbox message that says it failed and why, whatever `notify` is.

#### Scenario: A successful run

- **WHEN** a routine with `notify` true finishes
- **THEN** an inbox message appears with the reply

#### Scenario: Silenced

- **WHEN** a routine with `notify` false finishes
- **THEN** no inbox message is left, and the conversation is still there

#### Scenario: A failed run

- **WHEN** a run fails
- **THEN** an inbox message says the routine failed and gives the reason

### Requirement: A fire is not an approval

A run SHALL follow the same tool policy as a chat. A call that needs approval SHALL wait in the inbox for an answer, and the run SHALL continue after the answer. A fire SHALL NOT approve or pre-approve any call.

#### Scenario: An unattended ask

- **WHEN** a run calls a tool that needs approval and nobody is watching
- **THEN** an approval item waits in the inbox, the tool does not run, and the run continues once it is answered

### Requirement: The agent can manage routines

The agent SHALL have `schedule_routine`, `list_routines` and `cancel_routine` tools. `schedule_routine` SHALL take a name, a prompt, a cron expression or a time, and optionally a zone and `notify`, and SHALL create a routine with owner `agent`. `list_routines` SHALL return routines a page at a time with a `total` and a `next_cursor`. `cancel_routine` SHALL disable a routine by id.

#### Scenario: Scheduling

- **WHEN** the agent calls `schedule_routine` and the person approves
- **THEN** a routine exists with owner `agent`

#### Scenario: Cancelling

- **WHEN** the agent cancels a routine
- **THEN** it is listed as not enabled and does not fire

### Requirement: The agent's schedule waits for approval, every time

A `schedule_routine` call SHALL wait for a person's approval that shows the full prompt, the schedule, the zone and the conversation that proposed it. A saved "allow always" rule SHALL NOT cover it. If the person denies it, no routine SHALL be stored.

#### Scenario: Approval shows the prompt

- **WHEN** the agent proposes a routine
- **THEN** the approval item shows the prompt text and schedule exactly as they would run

#### Scenario: Denied

- **WHEN** the person denies the approval
- **THEN** no routine is stored and the agent is told it was denied

#### Scenario: A saved rule

- **WHEN** the person has previously chosen "allow always" for a `schedule_routine` call
- **THEN** the next `schedule_routine` call still waits for approval

### Requirement: A run started by a routine cannot create routines

The agent SHALL NOT be offered `schedule_routine` during a run that a routine started. It MAY still list and cancel routines.

#### Scenario: A routine tries to spawn another

- **WHEN** a routine's run asks for the tools it can use
- **THEN** `schedule_routine` is not among them

### Requirement: Agent-created routines are limited

A routine whose owner is `agent` SHALL NOT recur more often than every 15 minutes. At most 20 enabled routines with owner `agent` SHALL exist. A recurring one SHALL carry an `expires_at` 7 days after creation, SHALL stop firing then, and SHALL stay listed as expired until a person renews or deletes it. One-time routines and routines with owner `user` SHALL NOT expire. A person SHALL be able to set a routine as often as every 5 minutes.

#### Scenario: Too often

- **WHEN** the agent proposes a routine that recurs every 5 minutes
- **THEN** the call is rejected and names the 15-minute floor

#### Scenario: Too many

- **WHEN** 20 enabled agent routines exist and the agent proposes another
- **THEN** the call is rejected and names the cap

#### Scenario: Expiry

- **WHEN** an agent-created recurring routine is 7 days old
- **THEN** it stops firing and is listed as expired

#### Scenario: Renewal

- **WHEN** a person renews an expired routine
- **THEN** it fires again, with a new `expires_at` 7 days out

### Requirement: The web UI lists routines

The web UI SHALL have a Routines view that lists every routine with its name, schedule, owner, next run, last run and expiry, and lets a person pause, resume, run now, renew and delete one.

#### Scenario: Seeing what the agent set up

- **WHEN** the agent has created a routine
- **THEN** the Routines view lists it with owner `agent` and its expiry
