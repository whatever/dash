## Why

A page source flattens a feed into one item whose key is a hash of the page text, so any new entry changes the whole item and only the first 1,000 characters survive. A GitHub commits feed becomes one blob, cut off after the newest commit or two. Feeds already list their entries with stable ids, so each entry should be its own item.

## What Changes

- Add an `atom` source kind (`atom:<feed url>`). Each feed entry becomes one item keyed by its id, or its link when it has none.
- The Data panel treats a URL ending in `.atom` as a feed, the way it picks Hacker News and Bushwick Daily by host.
- A body that is not well-formed XML fails the check for that source and is reported like any other failed source.
- No change to existing kinds, the schedule, or how items are queued. Nothing is **BREAKING**.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `sources`: `atom` joins the supported kinds, and a new requirement describes its items.

## Impact

- Code: `sources/inputs/atom.py`, the `INPUTS` registry, `static/inputs/web.js`, and `tests/test_sources.py`.
- Operators: none. Existing sources are unaffected.
