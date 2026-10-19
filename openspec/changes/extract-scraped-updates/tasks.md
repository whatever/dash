## 1. Atom source

- [ ] 1.1 Add `atom:<url>` with one item per entry, keyed by id (link when absent). Verify: unit tests for entries with and without an id, and for a body that is not a feed.
- [ ] 1.2 Treat URLs ending in `.atom` as feeds in the data-sources panel. Verify: add a GitHub commits feed in the UI and see an `atom` source.

## 2. Extraction

- [ ] 2.1 Add a page-oriented extraction prompt and method to both memory clients. Verify: unit tests that parse its reply the same way as chat extraction.
- [ ] 2.2 Pass the extractor up to 8,000 characters of the item. Verify: a test with an item longer than the stored summary.
- [ ] 2.3 In the `update` handler, store one memory per extracted fact and skip facts within `DUPLICATE_DISTANCE`. Verify: worker tests for several facts, no facts, and a repeat.

## 3. Docs

- [ ] 3.1 Describe the new behaviour in the README's scrape section. Verify: the README matches the spec.
