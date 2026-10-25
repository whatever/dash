## ADDED Requirements

### Requirement: The agent can list sources

The agent SHALL have a `list_sources` tool that returns sources ordered by `id`, each with `id`, `kind`, `target`, `every_minutes`, `enabled` and `checked_at`. It SHALL accept an optional `kind`, `enabled`, `contains` (a case-insensitive part of the target), `limit` and `cursor`. `limit` SHALL default to 25 and SHALL NOT exceed 100.

#### Scenario: Filtering

- **WHEN** the agent lists with `kind` `hackernews` and `enabled` false
- **THEN** only disabled Hacker News sources are returned

#### Scenario: A limit above the maximum

- **WHEN** the agent lists with `limit` 500
- **THEN** the call is rejected and names the maximum of 100

### Requirement: A listing says how much there is and how to continue

The result of `list_sources` SHALL include `total`, the number of sources matching the filters whatever the page, and `next_cursor`, which SHALL be present only when more sources match.

#### Scenario: A short list

- **WHEN** the agent lists sources and 3 exist
- **THEN** the result holds all 3, `total` is 3 and there is no `next_cursor`

#### Scenario: Total follows the filter

- **WHEN** 41 sources exist, 3 of them `hackernews`, and the agent lists with `kind` `hackernews`
- **THEN** `total` is 3

#### Scenario: Walking the pages

- **WHEN** 60 sources exist and the agent lists them with `limit` 25 and then passes each `next_cursor` back
- **THEN** it receives pages of 25, 25 and 10 sources, every source exactly once, and the last page has no `next_cursor`

### Requirement: A page is bounded in size

The tool SHALL end a page early when its text would pass 20,000 characters, and `next_cursor` SHALL then continue from the last source returned. A page SHALL hold at least one source.

#### Scenario: Long targets

- **WHEN** the next 25 sources each have a 2,000-character target
- **THEN** the page holds fewer than 25 sources, stays within 20,000 characters, and has a `next_cursor` that continues from the last one returned

### Requirement: A cursor is stable and opaque

A cursor SHALL continue after the last source returned, whatever was added or removed since. The tool SHALL reject a cursor it did not issue with an error that tells the agent to repeat the call without one, and SHALL NOT return an empty page for it.

#### Scenario: A source is added mid-walk

- **WHEN** the agent has read the first page and a source is then added with an `id` above the page's last
- **THEN** continuing with `next_cursor` returns the rest in order, including the new source, and repeats none

#### Scenario: A source is removed mid-walk

- **WHEN** the source the cursor points after is deleted before the agent continues
- **THEN** the next page starts at the first source with a higher `id`

#### Scenario: A bad cursor

- **WHEN** the agent passes a cursor that is not one the tool issued
- **THEN** the call returns an error saying to start again without a cursor

### Requirement: The agent can add and change sources

The agent SHALL have an `add_source` tool taking `kind`, `target` and optional `every_minutes`, and a `change_source` tool taking an `id` and optional `enabled` and `every_minutes`. Both SHALL follow the same rules and limits as the HTTP API for sources, including the `web` URL rule, the interval range, and adding an existing source updating it.

#### Scenario: Add a page

- **WHEN** the agent calls `add_source` for a `web` page and the call runs
- **THEN** the source is stored, enabled, with the default interval of 60 minutes unless one was given

#### Scenario: Invalid source

- **WHEN** the agent calls `add_source` with a `web` target that is not an http or https URL
- **THEN** the call fails with the same message as the HTTP API and nothing is stored

#### Scenario: Pause a source

- **WHEN** the agent calls `change_source` with `enabled` false and the call runs
- **THEN** the source is listed as not enabled and is not checked

#### Scenario: Unknown source

- **WHEN** the agent calls `change_source` with an `id` that is not stored
- **THEN** the call fails and says the source does not exist

### Requirement: Changing sources waits for approval

By default each `add_source` and `change_source` call SHALL wait for a person's approval before it runs, and the approval SHALL show the kind, target and interval.

#### Scenario: Approved

- **WHEN** the agent calls `add_source` and the person approves
- **THEN** the source is stored

#### Scenario: Not approved

- **WHEN** the person denies an `add_source` call
- **THEN** nothing is stored and the agent is told the call was denied

### Requirement: The agent cannot delete a source

The agent SHALL NOT be offered a tool that deletes a source.

#### Scenario: Asking to remove one

- **WHEN** the agent wants a source to stop being checked
- **THEN** it can set `enabled` false with `change_source`, and the row stays listed
