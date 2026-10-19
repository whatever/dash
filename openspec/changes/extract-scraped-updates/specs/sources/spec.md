## MODIFIED Requirements

### Requirement: An update job stores the item as a memory

When the worker processes an `update` job, it SHALL ask the extraction model for the notable facts or changes in the item, as standalone sentences about the item's subject rather than about the user, and SHALL receive up to 8,000 characters of the item's text. It SHALL embed each fact and, unless a stored memory is within cosine distance 0.08 of it, store it as its own memory with source `scrape` and the tags `<kind>` and `<kind>:<target>`. It SHALL append a `done` event whose `stored` field is true when at least one fact was stored.

#### Scenario: New item

- **WHEN** the model returns three facts for an item and none is within 0.08 of a stored memory
- **THEN** three memories with source `scrape` are stored and the job ends with `done` and `stored` true

#### Scenario: Near-duplicate item

- **WHEN** every extracted fact is within 0.08 of a stored memory
- **THEN** nothing is stored and the job ends with `done` and `stored` false

#### Scenario: Nothing worth keeping

- **WHEN** the model returns no facts
- **THEN** no memory is stored and the job ends with `done` and `stored` false

#### Scenario: Partly repeated

- **WHEN** one of three extracted facts is within 0.08 of a stored memory
- **THEN** the other two are stored
