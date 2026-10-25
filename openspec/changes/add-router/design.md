## Context

`Worker.handle` writes every job to the `timeline` table, then branches on `kind`: `update` goes to `handle_update` (embed, skip near-duplicates, store a memory), and anything else goes to `handle_chat`. Duplicate items are already dropped twice:
- `dash scrape` keeps a 30-day seen key per item.
- `handle_update` skips anything within cosine distance 0.08 of a stored memory.

Memory extraction already uses a cheap Bedrock model behind the `Extractor` protocol.

The same router pattern runs in another project as a stage pipeline: dedupe → thread binding → rules → model → ask the person. This change builds the first useful part of it, and leaves room for the rest.

## Goals / Non-Goals

**Goals**
- Every inbound job has one recorded decision that a person can read in Live.
- Updates that aren't worth keeping stop going into memory.
- A wrong or failed model call never loses an item that would be stored today.

**Non-Goals**
- Routing replies to a running session, asking the person, other engines, budgets.
- Moving the existing dedupe into the router.
- Changing the Redis job format.

## Decisions

**Route inside the worker, after the timeline write.** `handle` records the entry as today, calls `route(job)`, writes the decision onto the same entry, then acts on it. Live shows the job at once, and its decision a moment later.
- Alternative: a separate router consumer between `dash:jobs` and the work. That adds a stream and a service before there is more than one kind of work to route to.

**Stages return a decision or pass.** Each stage takes the job and returns a decision or nothing, and the first decision wins. The stages are `rules`, then `model` (updates only, when `ROUTER_TRIAGE` is on), then `fallback`. Later stages (thread binding, ask) slot into the same list.

**Fallback is today's behaviour.** `fallback` always returns `remember`. A model decision below `ROUTER_MIN_CONFIDENCE` is replaced by `fallback`, with the model's guess kept in the reason, so a doubtful model never drops an item.

**Triage reuses the extraction model.** A `Triager` protocol next to `Extractor`, with a Bedrock implementation on `EXTRACT_MODEL`, temperature 0 and a JSON reply of `action`, `confidence` and `reason`. Anything malformed, or an action outside the three, counts as a failure.

**Item text is untrusted.** The prompt wraps the item in random markers that change on every call, and says the text between them is data, never instructions. The reason stored for a failure names only the kind of failure, never exception text.

**Decisions are columns, not JSON.** `timeline` gains nullable `action`, `routed_by`, `confidence` and `reason`, so Live and later queries can filter on them. Entries from before the change keep nulls.

**`flag` is the hook for the inbox.** For now, a flag stores the memory with the tag `flagged` and highlights the entry in Live. Once `add-inbox` lands, a flag can also open a message item. That isn't part of this change.

## Risks / Trade-offs

- **The model ignores something the person wanted.** Triage is off by default, the threshold falls back to storing, and the eval command measures the error before it's turned on.
- **Instructions inside an item steer the triage.** The text is fenced, the only possible outcomes are the three actions, and the eval set includes an injection case.
- **The extraction model isn't good enough for triage.** The eval tells us. A separate `ROUTER_MODEL` setting can follow if needed.

## Migration Plan

One migration adds the columns. It is reversible, and old rows need no backfill.
