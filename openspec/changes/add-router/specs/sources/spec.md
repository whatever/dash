## ADDED Requirements

### Requirement: A source can carry a fixed route

A source SHALL have an optional `route` of `ignore`, `remember` or `flag`, null by default, and listed with the source. A client SHALL be able to set or clear it when adding or updating a source. Any other value SHALL be rejected with 422.

#### Scenario: Set a route

- **WHEN** a client sets a source's route to `flag`
- **THEN** the source is listed with route `flag`

#### Scenario: Unknown route

- **WHEN** a client sets a route of `delete`
- **THEN** the response is 422 and the source is unchanged

## MODIFIED Requirements

### Requirement: An update job stores the item as a memory

When the worker processes an `update` job, it SHALL act on the job's routing decision:
- **`ignore`:** store nothing, and append a `done` event with `stored` false.
- **`remember` or `flag`:** embed the item's text, which names the source, published time, title, summary and URL. If a stored memory is within cosine distance 0.08 of it, store nothing. Otherwise store the text as a memory with source `scrape` and the tags `<kind>` and `<kind>:<target>`, plus `flagged` when the action is `flag`. Either way, append a `done` event whose `stored` field says which happened.

#### Scenario: New item

- **WHEN** an update decided as `remember` is not within 0.08 of any stored memory
- **THEN** a memory with source `scrape` is stored and the job ends with `done` and `stored` true

#### Scenario: Near-duplicate item

- **WHEN** an update's text is within 0.08 of a stored memory
- **THEN** nothing is stored and the job ends with `done` and `stored` false

#### Scenario: Ignored item

- **WHEN** an update is decided as `ignore`
- **THEN** nothing is embedded or stored and the job ends with `done` and `stored` false

#### Scenario: Flagged item

- **WHEN** an update decided as `flag` is not within 0.08 of any stored memory
- **THEN** a memory is stored with the tag `flagged`
