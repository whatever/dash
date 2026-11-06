## ADDED Requirements

### Requirement: Every inbound job gets one routing decision

Before acting on a job, the worker SHALL decide what to do with it. A decision SHALL have:
- an `action`: `chat`, `remember`, `flag` or `ignore`
- a `routed_by`: `rules`, `model` or `fallback`
- a `confidence` between 0 and 1, or none
- a `reason` of at most 200 characters

The worker SHALL record the decision on the job's timeline entry before carrying it out.

#### Scenario: A chat job

- **WHEN** the worker picks up a chat job
- **THEN** its decision is `chat`, routed by `rules`, with no confidence, and no model is called

#### Scenario: An update with nothing else to decide

- **WHEN** the worker picks up an update whose source has no route, and triage is off
- **THEN** its decision is `remember`, routed by `fallback`

### Requirement: A source's route decides its updates

When an update's source has a `route`, the decision SHALL be that route, routed by `rules`, and no model SHALL be called.

#### Scenario: A source set to flag

- **WHEN** an update arrives from a source whose route is `flag`
- **THEN** its decision is `flag`, routed by `rules`

### Requirement: The model triages the remaining updates

When `ROUTER_TRIAGE` is on, an update with no source route SHALL be triaged by the extraction model into `ignore`, `remember` or `flag`, with a confidence and a reason, routed by `model`. The item's text SHALL be marked in the prompt as untrusted data.

#### Scenario: A confident triage

- **WHEN** the model returns `ignore` with confidence 0.93
- **THEN** the decision is `ignore`, routed by `model`, with confidence 0.93

#### Scenario: Instructions inside an item

- **WHEN** an item's summary says to flag everything
- **THEN** the decision is still one of the three actions, and the item's instructions are not followed

### Requirement: An unsure or failed triage keeps today's behaviour

A model decision below `ROUTER_MIN_CONFIDENCE` (default 0.8), a malformed reply, an unknown action or a failed call SHALL produce `remember`, routed by `fallback`. The reason SHALL name the model's guess and confidence, or the kind of failure, without exception text.

#### Scenario: Low confidence

- **WHEN** the model returns `ignore` with confidence 0.62
- **THEN** the decision is `remember`, routed by `fallback`, and the reason names `ignore` and 0.62

#### Scenario: The model call fails

- **WHEN** the triage call times out
- **THEN** the decision is `remember`, routed by `fallback`

### Requirement: Triage can be measured

`dash eval-router <file>` SHALL read JSON lines, each an item with an expected action. It SHALL run the router on each, and print the count for each pair of expected and actual action, plus overall accuracy. It SHALL NOT store memories or timeline entries.

#### Scenario: Running the eval

- **WHEN** the eval runs on a file of ten items, nine decided as expected
- **THEN** it prints 90% accuracy, and no memory or timeline entry is added
