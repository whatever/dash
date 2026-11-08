## Why

The Data panel is the only way to see or change which sources dash checks. The agent can't answer "do I already follow Hacker News?" or "what did I set that page to?", and can't add a source when asked in chat. Today a person has to open the panel and do it.

This change proposes agent tools over the existing sources. Reading is cheap and safe. Changing a source makes dash fetch a URL on a schedule, so those tools ask first.

## What Changes

- Add a `list_sources` tool. It returns sources a page at a time, filtered by `kind`, `enabled` or text in the target, with a `total` and a `next_cursor` to continue.
- Add `add_source` and `change_source` tools. Both wait for a person's approval before they run.
- A page is cut to stay within a response size, so a few long targets can't flood the model's context.
- Nothing is **BREAKING**. The HTTP API and the Data panel are unchanged, and the tools use the same rules and limits.

Out of scope: deleting a source (pausing one is reversible, deleting is not), running a scrape from chat, and merging sources with scheduled routines (see `design.md`).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `sources`: adds the three agent tools and their paging.

This change is written against the agent tools proposed in whatever/dash#36 to #40. It refers to their ideas, not their specs, so it can be read and validated on its own. Once they land, the requirements here should move to the `agent-tools` spec.

## Impact

- Code: three tools beside the memory and inbox tools, and a keyset query on the sources table. No migration.
- Operators: `AGENT_TOOL_POLICY` can set `add_source` and `change_source` to `auto` or `never`. `list_sources` is `auto` unless set otherwise.
- Security: a source's target is text from the person or the agent. The tools reuse the existing validation, so a `web` source still needs an http or https URL.
