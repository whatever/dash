## Context

The format follows Anthropic's knowledge-wiki quickstart and its organizer prompt: pages with `name` and `description` frontmatter, an `_index.md` of one line per page, `[[slug]]` links, a dated "was X until" note for a corrected fact, and a `CONFLICT:` mark for claims no one can rank. Dreaming reads finished conversations and new memories and folds them into the pages. The wiki builds on the per-conversation workspaces of [dash #61](https://github.com/whatever/dash/pull/61): it is a `shared` mount.

## Decisions

### Files are the notes, git is the audit trail

Pages live in `/config/shared/wiki`, a git repository on the sandbox volume. Chat mounts it read-only, so a chat can read but not write. A dream mounts it read-write. After a dream the worker commits everything in one commit, so any dream can be reviewed with `git show` or undone with `git revert`. The agent is told not to commit; the system does it, so the history has one author and one entry per dream.

### Flat directory, no stubs

The quickstart leaves a `MOVED TO` stub when pages merge because its store cannot delete files. Git can, so dash has none. A flat directory keeps the lint, the index and the read-back simple. Subdirectories can come later.

### The schema is a file dash owns

`WIKI.md` holds the rules. The worker rewrites it before every dream, so a dream cannot drift the format and an operator reads the rules where the agent does.

### Lint, report, do not block

After a dream the worker reads the pages and checks them: frontmatter present, `name` equal to the file name, a description, every `[[link]]` resolving, the index listing every page and nothing else, each page under 100 KB. Anything in the repository that is not a page, such as a stray symlink or a scratch file, is reported the same way. Problems go in the inbox note. The commit still happens, because git already makes a bad dream recoverable and blocking would stall the next one.

### What a dream may do

A dream runs as an ordinary turn in a conversation titled `Dream <date>`, so it shows in the chat list and keeps its history. It runs on its own agent, built without the web-search capability and with no MCP servers. Web search is a capability that brings its own tool (the model's native one, or a DuckDuckGo fallback), so neither the tool policy nor a per-turn tool limit can remove it; leaving it out of the agent does. The turn is also limited to `run_command`, which is pre-approved for it, and its profile has no GitHub token and mounts only the wiki. Transcripts are given as data inside tags and the instructions say never to follow them. Scraped pages reach transcripts, so a transcript is an injection route; the limits are what contain it.

### Chat reads through tools, not the shell

Chat is offered `read_wiki` and `search_wiki`. They read the repository directly, take a page name that is letters, digits, `-` and `_`, and need no approval, so reading notes does not wait in the inbox while `run_command` stays on `ask`. The read-only mount stays for sessions that use the shell.

### Memories are notes the dream folds in

The dream reads not only conversations but also memories added since the last dream. Scraped items, memories from the agent's `remember` tool, and memories added by hand all appear in a `<notes>` block alongside transcripts. A note is rendered as `- memory <id> (<source>, <date>): <content>`, and the dream is told to cite it as `(memory <id>, <source>, <date>)`. Transcripts win where they cover the same fact as a note, since conversations are richer. A memory is "folded in" through the existing last-dream window: the first dream that commits after a memory was added reads it. There is no new column and no migration.

### Scheduling

A CronJob runs `dash dream`, which queues one job and exits, like `dash scrape`. A Redis key keeps one dream queued at a time. The last-dream time advances only when a dream finishes and commits, so a failed one is read again next time. A dream with no conversations newer than the last one skips the model call.

### Recall stays on pgvector for now

Recalled memories still come from pgvector and are pasted into each chat turn, so a fact the wiki has corrected can still be recalled in its old form. Making the files the source of truth, with pgvector as an index rebuilt from them and a small dream-kept page in place of the raw recalled sentences, is a later change once the wiki has proved useful.

## Risks

- The dream is the first unattended agent that edits state. The separate agent, the tool limit, the single-commit history and the inbox note are the controls.
- Transcript text goes to the model that edits the wiki; with a hosted model that is already true of chat.
- Chat sessions copy the wiki before every command, which is fine for notes and not for a large directory.
- A very busy day can exceed the 60,000 characters of transcript. The newest conversations come first and the rest wait for the next dream, since the cut-off time only moves to the dream's start.

## Open Questions

- Should the dream run on a cheaper model than chat? Not configurable yet.
- Should the dream's inbox note ask for approval of the commit before it takes effect? Today it is applied and reviewable after.

### Memories are notes the dream folds in

Anthropic's memory layering has transcripts at the bottom, short notes above them, organized pages like this wiki above those, and a small layer loaded into every turn. Dreaming reads the lower layers and rewrites the upper ones. In dash the memories table is the notes layer: the post-turn extractor, the agent's `remember` tool, `dash scrape` and the person all write one sentence at a time. So a dream reads the memories added since the last dream as well as the transcripts. Scraped items reach the wiki only this way, since they are not conversations.

The window is the last-dream time that already gates conversations, so no column marks a memory as read: a memory is read once by the first dream that commits after it. Every source is included. Extracted facts repeat the transcripts, but a busy day can cut a transcript, and the dream is told the transcript wins where both cover a fact. Each note carries its id so a page can cite it.
