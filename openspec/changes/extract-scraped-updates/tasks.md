## 1. Extraction

- [ ] 1.1 Add a page-oriented extraction prompt and method to the memory client. Verify: unit tests that parse its reply the same way as chat extraction.
- [ ] 1.2 Pass the extractor up to 8,000 characters of the item. Verify: a test with an item longer than the stored summary.
- [ ] 1.3 In the `update` handler, store one memory per extracted fact and skip facts within `DUPLICATE_DISTANCE`. Verify: worker tests for several facts, no facts, and a repeat.

## 2. First check

- [ ] 2.1 In the scrape, queue only the first 10 items of a source none of whose items were seen, and mark the rest seen. Verify: tests for 500 items, 8 items, and a source that has been checked before.

## 3. Docs

- [ ] 3.1 Describe the new behaviour in the README's scrape section. Verify: the README matches the spec.
