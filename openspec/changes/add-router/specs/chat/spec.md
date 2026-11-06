## MODIFIED Requirements

### Requirement: Every job is recorded on a live timeline

Before handling a job, the worker SHALL record it with its job id, its kind (`chat` or `update`) and its data: a chat job's conversation id, an update job's item. Once the job is routed, the entry SHALL also carry the decision's `action`, `routed_by`, `confidence` and `reason`. The system SHALL list the newest 100 entries, newest first, at `/api/live`, each with its `id`, `kind`, `data`, creation time, and those four decision fields, which are null for an entry with no decision.

#### Scenario: A chat job appears

- **WHEN** the worker picks up a chat job
- **THEN** `/api/live` lists an entry of kind `chat` with that conversation's id, action `chat` and routed by `rules`

#### Scenario: An entry from before routing

- **WHEN** an entry was recorded before routing existed
- **THEN** `/api/live` lists it with null decision fields
