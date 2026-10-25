## Context

Sources live in the `sources` table, one row per `kind` and `target`, with `every_minutes`, `enabled` and `checked_at`. The HTTP API lists all of them in one response, which is fine for a panel. A tool result goes into the model's context, so it needs bounds the panel doesn't.

## Decisions

**Cursor paging, not page numbers.** This follows the Model Context Protocol's pagination model: an opaque cursor, a server-chosen page size, and no `next_cursor` at the end. Rows are ordered by `id`, so a cursor is the last id seen. A source added or removed between two calls can't shift a page, which an offset would do.

**The cursor is opaque to the model.** The tool description says to pass it back unchanged. A malformed or foreign cursor returns an error that says to start again without one, and never an empty page, so the model can't mistake a bad cursor for the end of the list.

**Two bounds on a page.** `limit` defaults to 25 and is at most 100, and the page is also cut at 20,000 characters, the same cap as `run_command` and `fetch_url`. A target can be 2,000 characters, so 100 of them would be 200,000. When the character cap ends a page early, `next_cursor` still continues from the last row returned.

**`total` counts the filter, not the page.** One `COUNT` lets the model say "3 of 41" and decide whether to filter or keep paging. It is computed without the cursor, so it stays the same across a walk.

**Compact rows.** `id`, `kind`, `target`, `every_minutes`, `enabled` and `checked_at`, the same fields as the HTTP API. Nothing else, so the result stays small.

**Writes ask first.** A source makes dash fetch a URL on a schedule, so `add_source` and `change_source` default to `ask` in the tool policy. The approval card shows the kind, target and interval. A rule saved by "Allow always" covers the exact call, as for other tools.

**No delete.** `change_source` can set `enabled` to false, which stops checks and keeps the row and its history. Deleting waits for a person in the Data panel.

## Open questions

- Is the 25-row default right? A single-user dash probably has under 25 sources, so paging may rarely trigger. It costs little, and it keeps the tool correct if sources grow.
- Should `list_sources` also report the last error for a source that failed? The table doesn't store one today, so this change leaves it out.
- Routines (a separate proposal) and sources both run on a schedule. Should a source become a kind of routine, so one panel and one set of tools cover both? That would migrate the sources table and change the `sources` spec, so it belongs in a conversation with the maintainer, not in this change.
