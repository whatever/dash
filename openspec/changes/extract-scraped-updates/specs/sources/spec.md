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

### Requirement: An item is queued once

A scrape SHALL queue an `update` job for an item only if its source and key have not been queued within the last 30 days. Marking an item as seen SHALL be atomic, so two scrapes at once queue it once. The scrape SHALL record, without expiry, that a source has been checked. The first check of a source, when no such record exists, SHALL queue only the first 10 items in the order the source returns them and mark the rest as seen without queuing them. Every later check SHALL queue all new items.

#### Scenario: Repeat item

- **WHEN** a scrape finds an item whose source and key were queued yesterday
- **THEN** no job is queued

#### Scenario: Seen for a month

- **WHEN** an item's source and key were last queued more than 30 days ago
- **THEN** a scrape queues it again

#### Scenario: First check of a long feed

- **WHEN** a source is checked for the first time and returns 500 items
- **THEN** 10 jobs are queued, and the other 490 items are marked seen so later scrapes do not queue them

#### Scenario: First check of a short source

- **WHEN** a source is checked for the first time and returns 8 items
- **THEN** all 8 are queued

#### Scenario: Later checks queue everything new

- **WHEN** a source that has been checked before returns 30 items not seen before
- **THEN** all 30 are queued

#### Scenario: Busy feed

- **WHEN** a source that has been checked before returns 20 entries, all new since the last check
- **THEN** all 20 are queued

#### Scenario: Long gap between checks

- **WHEN** a source is checked again after 60 days, when every seen item has expired
- **THEN** every item it returns is queued, not only the first 10
