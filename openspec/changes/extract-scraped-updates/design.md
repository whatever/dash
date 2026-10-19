## Context

`dash scrape` runs on a schedule. Each configured source fetches a page and returns items; an item is new when its key has not been seen. New items are queued as `update` jobs. The worker embeds `Item.text()`, skips it if it is within `DUPLICATE_DISTANCE` of an existing memory, and otherwise stores it. No model reads the text. `Item.summary` is capped at `SUMMARY_CHARS` (1,000) when the page is parsed.

Chat turns are different: after a reply the worker asks the extraction model for durable facts about the user and stores each fact as a memory.

## Goals / Non-Goals

**Goals**
- Store what a scraped item says as standalone facts that recall can match against.
- Work well on feeds, which the `add-atom-source` change turns into one item per entry.
- Keep the cheap gate: no model runs for an item already seen.

**Non-Goals**
- Replacing the deterministic sources with agent-driven fetching.
- Digests, summaries across runs, or any new output channel.
- Changing the schedule, the scrape CLI, or the data-sources UI beyond recognizing feed URLs.

## Decisions

**Extract in the worker, reusing the memory extractor.** The worker already holds an extraction client for chat. Adding a second method with a page-oriented prompt keeps the change small and uses the model the operator has already configured. Alternative: hand each item to a Hermes job (see Open questions).

**A separate prompt, not the chat prompt.** The chat prompt asks for facts about the user and would discard most of a changelog. The page prompt asks for notable facts or changes in the item, written as standalone sentences that name their subject, because a fact is recalled without the item around it.

**Facts are stored one per memory, tagged with the source.** This keeps recall granular and lets the existing embedding-distance check dedupe at the fact level. Memories keep `source="scrape"` and the tags they have today.

**The extractor sees up to 8,000 characters.** Chat already cuts each side at 8,000. Items carry the longer text only as far as the worker, and the stored memory is the extracted fact, not the page.

## Risks / Trade-offs

- A first scrape of a long feed makes one model call per entry. Operators who want to avoid that can start a source after the feed is mostly history, or a limit on entries per run could be added.
- Extraction can drop detail the raw text kept. The raw text is not stored, so a bad prompt loses information permanently.

## Open questions

**Should the model step be a Hermes job instead?** Hermes has scheduled jobs that are either script-only or run a fresh agent session with a prompt. A job can run a script first and emit `{"wakeAgent": false}` to skip the model when nothing changed, which is the shape `dash scrape` already has: a deterministic gate, then a model. If dash delegated extraction to a Hermes job it would get tool access, per-job model choice and delivery tracking, at the cost of depending on the Hermes scheduler running in the deployed pod. Is that a direction the project wants?

**Should dash write its own collectors from chat?** Sites differ, which is why Hacker News and Bushwick Daily have their own parsers. Agents are good at writing that kind of code, so dash could be asked to watch a site and write the collector itself. That raises design questions this change does not answer: where the code is stored and run (a writable scripts directory in the sandbox is one option), how a script is registered as a source kind, what output contract it must follow (`Item` as JSON on stdout), and how its permissions are limited to the site or tools it needs, the way an agent session's are.

**Should a run know what the last run produced?** Hermes jobs can feed a previous run's output into the next one. For a recurring digest that would let a run say what changed since last time. Nothing here needs it yet.

**Should extraction be optional?** This change makes it the default for every scraped item. A setting to keep the raw-text behaviour would be a small addition if existing operators want it.
