## MODIFIED Requirements

### Requirement: Relevant memories are recalled into each reply

Before answering a job, the worker SHALL embed the latest user message and look up the `MEMORY_TOP_K` nearest memories (default 8). It SHALL keep only those within cosine distance 0.65. If any remain, it SHALL emit a `memories` event and give them to the agent as instructions for that turn. The instructions SHALL tell the model to use the memories when relevant and not to mention the list unless asked. If none remain, it SHALL add no memory instructions and emit no event.

#### Scenario: Relevant memory

- **WHEN** a stored memory is within 0.65 of the user's message
- **THEN** the reply is generated with that memory in the turn's instructions, and the job has a `memories` event

#### Scenario: Nothing relevant

- **WHEN** no stored memory is within 0.65
- **THEN** the model request carries no memory instructions and the job has no `memories` event

#### Scenario: Recall fails

- **WHEN** embedding or searching raises an error
- **THEN** the error is logged and the reply proceeds as if nothing was recalled
