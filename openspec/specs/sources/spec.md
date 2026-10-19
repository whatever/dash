# sources Specification

## Purpose

Keep dash aware of the outside world. `dash scrape` checks configured sources for new items and queues each one as an `update` job, and the worker stores it as a memory.

## Requirements

### Requirement: Sources are configured by kind and target

The system SHALL let a client add a source with a `kind` (`web`, `hackernews` or `bushwick`), a `target` of 1 to 2,000 characters, and `every_minutes` between 5 and 10,080 (default 60), and SHALL return 201 with the source. A source SHALL be listed with its `id`, `kind`, `target`, `every_minutes`, `enabled` and `checked_at`.

#### Scenario: Add a page

- **WHEN** a client posts kind `web` and target `https://example.com/status`
- **THEN** the response is 201 and the source is listed, enabled, checked every 60 minutes and never checked

#### Scenario: Unknown kind or interval out of range

- **WHEN** a client posts a kind that is not supported, or `every_minutes` outside 5 to 10,080
- **THEN** the request is rejected and nothing is stored

### Requirement: A web source needs a URL, and a source exists once

A `web` source SHALL have a target starting with `http://` or `https://`. Adding a source that already exists with the same kind and target SHALL update its interval and enable it instead of creating a second one.

#### Scenario: Web source without a URL

- **WHEN** a client posts kind `web` with a target that is not an http or https URL
- **THEN** the response is 422 and nothing is stored

#### Scenario: Adding it again

- **WHEN** a client adds a source that already exists with a different interval
- **THEN** no second source is created, and the existing one takes the new interval and is enabled

### Requirement: Sources can be paused, retimed and removed

The system SHALL let a client change a source's `enabled` flag and `every_minutes`, returning the source, or 404 if there is none. It SHALL delete a source by id and return 204, or 404 if there is none.

#### Scenario: Pause

- **WHEN** a client sets `enabled` to false on a source
- **THEN** the source is listed as not enabled and is not checked

#### Scenario: Unknown source

- **WHEN** a client changes or deletes a source id that is not stored
- **THEN** the response is 404

### Requirement: A scrape checks the given sources and the stored sources that are due

`dash scrape` SHALL check every source passed with `--source` (or listed in `SCRAPE_SOURCES`), written `<kind>:<target>`, and, when `DATABASE_URL` is set, every stored source that is enabled and has either never been checked or was last checked at least `every_minutes` ago. After a run that is not a dry run it SHALL record the time on the stored sources it checked. With `--dry-run` it SHALL fetch and print new items without queuing them or recording the check.

#### Scenario: Due source

- **WHEN** a stored, enabled source was last checked longer ago than its interval
- **THEN** a scrape checks it and records the check time

#### Scenario: Not yet due

- **WHEN** a stored source was checked more recently than its interval
- **THEN** a scrape skips it

#### Scenario: Nothing to check

- **WHEN** no source is given and `DATABASE_URL` is unset
- **THEN** the command fails with a usage error

#### Scenario: Bad source spec

- **WHEN** a `--source` value does not name a supported kind followed by `:` and a target
- **THEN** the command fails and names the supported kinds

### Requirement: A web page is one item

A `web` source SHALL return one item for the page, titled by its `<title>` (or its URL) and summarized by the first 1,000 characters of its visible text, keyed by a hash of that text. Items SHALL carry a source, key, title, URL, summary and published time.

#### Scenario: Page changes

- **WHEN** a `web` page's visible text changes between scrapes
- **THEN** its item has a new key

### Requirement: Listing sites give one item per entry

A `hackernews` source SHALL return one item per story on the listing page, keyed by the story's Hacker News id, with its points, comment count and discussion link in the summary. A `bushwick` source SHALL return one item per article teaser on the page, keyed by the article's URL.

#### Scenario: Listing page

- **WHEN** a Hacker News front page with thirty stories is fetched
- **THEN** thirty items are returned, one per story

### Requirement: An item is queued once

A scrape SHALL queue an `update` job for an item only if its source and key have not been queued within the last 30 days. Marking an item as seen SHALL be atomic, so two scrapes at once queue it once.

#### Scenario: Repeat item

- **WHEN** a scrape finds an item whose source and key were queued yesterday
- **THEN** no job is queued

#### Scenario: Seen for a month

- **WHEN** an item's source and key were last queued more than 30 days ago
- **THEN** a scrape queues it again

### Requirement: One failing source does not stop the others

A scrape SHALL check all sources even when some fail, report each failure with its source, and exit with an error only when every source it checked failed.

#### Scenario: One of three fails

- **WHEN** one source raises an error and two succeed
- **THEN** the other two are checked and queued, the failure is reported, and the command exits successfully

#### Scenario: All fail

- **WHEN** every checked source raises an error
- **THEN** the command exits with an error

### Requirement: An update job stores the item as a memory

When the worker processes an `update` job, it SHALL embed the item's text, which names the source, published time, title, summary and URL. If a stored memory is within cosine distance 0.08 of it, the worker SHALL store nothing. Otherwise it SHALL store the text as a memory with source `scrape` and the tags `<kind>` and `<kind>:<target>`. Either way it SHALL append a `done` event whose `stored` field says which happened.

#### Scenario: New item

- **WHEN** an update's text is not within 0.08 of any stored memory
- **THEN** a memory with source `scrape` is stored and the job ends with `done` and `stored` true

#### Scenario: Near-duplicate item

- **WHEN** an update's text is within 0.08 of a stored memory
- **THEN** nothing is stored and the job ends with `done` and `stored` false
