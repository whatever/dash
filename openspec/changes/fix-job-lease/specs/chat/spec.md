## MODIFIED Requirements

### Requirement: Jobs survive worker failure

The queue SHALL give each job to one worker at a time and remove it only after the worker finishes it, with a reply or an error. A worker SHALL renew its claim on a running job every 30 seconds. A job held unfinished and not renewed for two minutes SHALL be given to another worker. A worker that cannot reach the queue SHALL keep running and retry every two seconds.

#### Scenario: Worker dies mid-job

- **WHEN** a worker takes a job and stops without finishing it
- **THEN** after two minutes another worker takes the job

#### Scenario: A long job is not taken

- **WHEN** a worker runs a job for longer than two minutes and keeps renewing its claim
- **THEN** no other worker takes the job

#### Scenario: Queue outage

- **WHEN** the queue is unreachable and then recovers
- **THEN** the worker resumes taking jobs without being restarted

### Requirement: Queue status

The system SHALL report the number of waiting jobs, jobs in flight, and workers at `/api/queue`. A worker SHALL count only while it has been active in the last minute, and the queue SHALL delete workers that have been idle for an hour and hold no job.

#### Scenario: One job running

- **WHEN** one worker holds one job and none are waiting
- **THEN** the report shows `in_flight` 1, `waiting` 0 and `workers` 1

#### Scenario: A worker that was replaced

- **WHEN** the worker pod restarts and the previous worker has been idle for over a minute
- **THEN** the report counts one worker, not two

## ADDED Requirements

### Requirement: A job that runs too long is stopped

The worker SHALL stop a job that runs longer than `JOB_TIMEOUT_SECONDS` (default 1800), emit an `error` event with the message "The job timed out.", and remove the job from the queue without retrying it. It SHALL log how long each job took, and warn when one took more than five minutes.

#### Scenario: A job that never returns

- **WHEN** a job runs past the limit
- **THEN** its events end with the error "The job timed out." and no other worker takes it

#### Scenario: A job that already ended

- **WHEN** the limit passes after a job has emitted `done`
- **THEN** no second ending event is added
