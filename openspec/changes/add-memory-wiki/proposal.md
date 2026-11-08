## Why

Memories are one embedded sentence each. They keep no source, cannot record that a fact changed or that two conversations disagree, and nothing ever tidies them. A person cannot read them as a whole, and neither can another agent. Notes kept as plain markdown in git can be read, diffed, corrected by hand and shared with any tool, and a periodic "dream" over recent conversations can keep them current.

## What Changes

- Add a wiki: flat markdown pages with frontmatter, an index and `[[links]]`, in a git repository in the sandbox, described by a `WIKI.md` that dash writes into it.
- Chat sessions get the wiki read-only at `wiki/` and are told to read its index for questions about the person.
- Add a `dream` job and a `dash dream` command, run nightly by a CronJob. It reads the conversations since the last dream and has the agent update the wiki, with no tool but `run_command`, no GitHub token, and only the wiki mounted.
- Each dream leaves its trace: a conversation, one git commit, and an inbox note with the diffstat and any format problems.
- Off by default (`WIKI=on`, chart `wiki.enabled`). The existing pgvector memories are unchanged.

## Capabilities

### New Capabilities

- `wiki`: the page format, how chat reads it, and how dreaming updates it.

### Modified Capabilities

None.

## Impact

- Code: `wiki.py`, the worker's `dream` handling, `queue.py` (dream job and last-dream time), the `dash dream` command, the tool limit in the policy, config, a CronJob in the chart, and tests.
- Operators: `WIKI`, chart `wiki.enabled` and `wiki.schedule`. It needs the sandbox and [dash #61](https://github.com/whatever/dash/pull/61) (session workspaces).
- Out of scope: making the wiki the source of truth for recall (pgvector stays), editing pages in the UI, and a wiki search tool.
