# AGENTS.md

## Code style

- Use list, dict, and set comprehensions and generator expressions instead of `for` loops, especially loops that call `.append()`.
- Do not write comments in generated code. Tool pragmas such as `# noqa` and `# type: ignore` are permitted.
- Write one-line docstrings in the imperative mood. Start with the verb that matches what the callable does:

| Callable | Verb | Example |
| :- | :- | :- |
| Returns a value | Return | `"""Return the user with the given ID."""` |
| Returns a bool | Return True if | `"""Return True if the job is finished."""` |
| Generator | Yield | `"""Yield each memory that matches the query."""` |
| Side effect, returns None | Specific action verb | `"""Delete expired jobs from the queue."""` |
| Raises only (a validator) | Raise | `"""Raise ValueError if the token is expired."""` |
| Class | Noun phrase | `"""A queued job and its status."""` |

## PR style

- use semantic pull request titles with `{fix,feat,chore}`
- keep descriptions simple and up-to-date

## PR size and scope

- One concern per PR. Don't mix a proposal (openspec) with its implementation.
- Aim for under 400 changed lines, excluding lockfiles and generated files. Over 1000, split or stack the PR; the reviewer skips it otherwise.
- Stack large work as a chain of PRs, each reviewable and revertable on its own.
- Close a PR you replace instead of opening a duplicate.

## Review rounds

- The dash reviewer reviews a PR at most 3 times. If it is still finding problems, stop pushing fixes and rethink the approach or ask a human.
- Fix every instance of a reported class of bug in one push, not one line per round.
- See CONTRIBUTING.md for which changes need a human reviewer.
