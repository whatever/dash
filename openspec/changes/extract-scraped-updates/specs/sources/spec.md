## ADDED Requirements

### Requirement: An Atom feed yields one item per entry

The system SHALL accept sources of kind `atom` whose target is the URL of an Atom feed, and SHALL return one item per `entry`. An item's key SHALL be the entry's `id`, or its link when it has no `id`. Its title SHALL be the entry's title, its URL the entry's `alternate` link (or first link), its summary the entry's `content` or else `summary` with markup removed, and its published time the entry's `published` or else `updated` value.

#### Scenario: Entries become items

- **WHEN** a feed with two entries, each with an `id`, is fetched
- **THEN** two items are returned, keyed by those ids

#### Scenario: Entry without an id

- **WHEN** an entry has no `id`
- **THEN** its item is keyed by its link

#### Scenario: Not a feed

- **WHEN** the body at the target is not well-formed XML
- **THEN** the check for that source fails and is reported, and other sources are unaffected

### Requirement: Scraped items are distilled into facts before they are stored

When an `update` job is processed, the system SHALL ask the extraction model for the notable facts or changes in the item, as standalone sentences about the item's subject rather than about the user, and SHALL store each fact as its own memory with source `scrape`. The extraction model SHALL receive up to 8,000 characters of the item's text.

#### Scenario: Facts stored

- **WHEN** the model returns three facts for an item
- **THEN** three memories are stored, each embedded separately

#### Scenario: Nothing worth keeping

- **WHEN** the model returns no facts
- **THEN** no memory is stored and the job completes

#### Scenario: Repeated fact

- **WHEN** an extracted fact is within the duplicate distance of an existing memory
- **THEN** that fact is not stored and the others are

### Requirement: An item is only extracted once

An item SHALL reach the extraction model only when its key has not been seen for its source, so a page or entry that has not changed does not cost a model call.

#### Scenario: Unchanged item

- **WHEN** a scrape finds an item whose key was already enqueued
- **THEN** no job is queued and no model is called
