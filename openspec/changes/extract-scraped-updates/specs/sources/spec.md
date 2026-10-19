## MODIFIED Requirements

### Requirement: Sources are configured by kind and target

The system SHALL let a client add a source with a `kind` (`web`, `atom`, `hackernews` or `bushwick`), a `target` of 1 to 2,000 characters, and `every_minutes` between 5 and 10,080 (default 60), and SHALL return 201 with the source. A source SHALL be listed with its `id`, `kind`, `target`, `every_minutes`, `enabled` and `checked_at`.

#### Scenario: Add a page

- **WHEN** a client posts kind `web` and target `https://example.com/status`
- **THEN** the response is 201 and the source is listed, enabled, checked every 60 minutes and never checked

#### Scenario: Add a feed

- **WHEN** a client posts kind `atom` and target `https://github.com/acme/app/commits/main.atom`
- **THEN** the response is 201 and the source is listed with kind `atom`

#### Scenario: Unknown kind or interval out of range

- **WHEN** a client posts a kind that is not supported, or `every_minutes` outside 5 to 10,080
- **THEN** the request is rejected and nothing is stored

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

## ADDED Requirements

### Requirement: An Atom feed yields one item per entry

An `atom` source SHALL return one item per `entry` of the feed at its target. An item's key SHALL be the entry's `id`, or its link when it has no `id`. Its title SHALL be the entry's title, its URL the entry's `alternate` link (or first link), its summary the entry's `content` or else `summary` with markup removed, and its published time the entry's `published` or else `updated` value.

#### Scenario: Entries become items

- **WHEN** a feed with two entries, each with an `id`, is fetched
- **THEN** two items are returned, keyed by those ids

#### Scenario: Entry without an id

- **WHEN** an entry has no `id`
- **THEN** its item is keyed by its link

#### Scenario: Not a feed

- **WHEN** the body at the target is not well-formed XML
- **THEN** the check for that source fails and is reported, and other sources are unaffected
