## 1. The wiki

- [x] 1.1 Write the page format, `WIKI.md`, and the lint. Verify: unit tests for each lint rule.
- [x] 1.2 Seed, commit and list pages in the sandbox repository. Verify: tests run it against a real local git repository.
- [x] 1.3 Mount the wiki read-only for chat and read-write for dreams, and point chat at the index. Verify: tests for the profiles and the chat instructions.
- [x] 1.4 Add `read_wiki` and `search_wiki` tools. Verify: tests read the index, a page and a search, and refuse a name with `/` or `..`.

## 2. Dreaming

- [x] 2.1 Add the `dream` job kind, the one-at-a-time lock, the last-dream time and `dash dream`. Verify: tests for the lock and the time.
- [x] 2.2 Run dreams on their own agent with no web search and no MCP servers, limited to `run_command`, pre-approved, with no GitHub token. Verify: the model is offered only `run_command`, and a dream never uses the chat agent.
- [x] 2.3 Fold recent conversations into the wiki, commit, lint and leave an inbox note. Verify: a scripted dream writes a page, and the note names it and the lint problems.
- [x] 2.4 Skip the model call when nothing is new. Verify: no model request is made.
- [x] 2.5 Fold new memories into the wiki. Verify: memories added since the last dream reach the notes block.

## 3. Operators

- [x] 3.1 Add `wiki.enabled` and `wiki.schedule`, the `dash-dream` CronJob and `WIKI` to the chart and compose. Verify: `helm template` renders nothing by default and the CronJob when enabled.
- [ ] 3.2 Run a dream against the real sandbox image and read the commit. Verify: `git log` in the sandbox shows one commit and the inbox note matches it.
