## Why

`dash scrape` stores each new item as a memory without any model reading it. A page source keeps its first 1,000 characters of text, so a long page or a busy feed is cut off after the first entry or two, and what is stored is raw page text rather than something recall can use well. A changelog or release feed cannot be summarized or searched properly from that.

## What Changes

- Build on the `atom` source kind from the `add-atom-source` change, so feeds give one item per entry.
- Run each scraped item through the fact-extraction model before it is stored. A page-oriented prompt asks for the notable facts or changes in the item, not facts about the user. Each fact becomes its own memory, and the existing duplicate check applies per fact.
- Give the extractor more of the page than the stored summary keeps, up to a fixed cap.
- Sources that produce nothing worth keeping store nothing, so an unchanged-in-substance page costs one model call and no memory.
- No change to how items are found: gating still happens before any model runs, because an item only reaches the worker when its key is new.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `sources`: the `update` job stores extracted facts instead of the raw item text.

## Impact

- Code: the `update` handler in `worker.py`, a new extraction prompt and method in `memory.py`, and `tests/`.
- Cost: one extraction call per new scraped item. A first scrape of a feed makes one call per entry.
- Operators: no new settings are required. `EXTRACT_MODEL` already names the model.
- Open design questions are in `design.md`. The two largest, whether this step should be a Hermes job and whether dash should write its own collectors, are not decided by this change.
