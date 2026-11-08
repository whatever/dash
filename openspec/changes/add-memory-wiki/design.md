## Context

The format follows Anthropic's knowledge-wiki quickstart and its organizer prompt: pages with `name` and `description` frontmatter, an `_index.md` of one line per page, `[[slug]]` links, a dated "was X until" note for a corrected fact, and a `CONFLICT:` mark for claims no one can rank. Dreaming reads finished conversations and folds them into the pages. The wiki builds on the per-conversation workspaces of [dash #61](https://github.com/whatever/dash/pull/61): it is a `shared` mount.

## Decisions

### Files are the notes, git is the audit trail

Pages live in `/config/shared/wiki`, a git repository on the sandbox volume. Chat mounts it read-only, so a chat can read but not write. A dream mounts it read-write. After a dream the worker commits everything in one commit, so any dream can be reviewed with `git show` or undone with `git revert`. The agent is told not to commit; the system does it, so the history has one author and one entry per dream.

### Flat directory, no stubs

The quickstart leaves a `MOVED TO` stub when pages merge because its store cannot delete files. Git can, so dash has none. A flat directory keeps the lint, the index and the read-back simple. Subdirectories can come later.

### The schema is a file dash owns

`WIKI.md` holds the rules. The worker rewrites it before every dream, so a dream cannot drift the format and an operator reads the rules where the agent does.

### Lint, report, do not block

After a dream the worker reads the pages and checks them: frontmatter present, `name` equal to the file name, a description, every `[[link]]` resolving, the index listing every page and nothing else, each page under 100 KB. Problems go in the inbox note. The commit still happens, because git already makes a bad dream recoverable and blocking would stall the next one.

### What a dream may do

A dream runs as an ordinary turn in a conversation titled `Dream <date>`, so it shows in the chat list and keeps its history. Its turn is limited to `run_command` through a new tool limit on the turn, `run_command` is pre-approved for it, and its profile has no GitHub token and mounts only the wiki. Transcripts are given as data inside tags and the instructions say never to follow them. Scraped pages reach transcripts, so a transcript is an injection route; the limits are what contain it. The model's own web search is a capability, not a toolset, and this limit may not cover it. That needs checking before the dream runs on untrusted input.

### Scheduling

A CronJob runs `dash dream`, which queues one job and exits, like `dash scrape`. A Redis key keeps one dream queued at a time. The last-dream time advances only when a dream finishes and commits, so a failed one is read again next time. A dream with no conversations newer than the last one skips the model call.

### Recall stays on pgvector for now

The wiki is read by the agent through the filesystem. Recalled memories still come from pgvector and the post-turn fact extractor. Making the files the source of truth, with pgvector as an index rebuilt from them, is a later change once the wiki has proved useful.

## Risks

- The dream is the first unattended agent that edits state. The tool limit, the single-commit history and the inbox note are the controls.
- Transcript text goes to the model that edits the wiki; with a hosted model that is already true of chat.
- Chat sessions copy the wiki before every command, which is fine for notes and not for a large directory.
- A very busy day can exceed the 60,000 characters of transcript. The newest conversations come first and the rest wait for the next dream, since the cut-off time only moves to the dream's start.

## Open Questions

- Should the dream run on a cheaper model than chat? Not configurable yet.
- Should the dream's inbox note ask for approval of the commit before it takes effect? Today it is applied and reviewable after.
