## Why

Every conversation runs commands in the same `/config/workspace`, so one chat's clones, scratch files and half-finished edits sit in the next chat's way, and nothing says which repositories or notes a kind of session may see. Giving each conversation its own directory, built from a named profile of mounts, is the seam that lets a wiki, a research checkout or a read-only repository be offered to some sessions and not others.

## What Changes

- **BREAKING** `run_command` runs in a directory of its own per conversation, `/config/workspace/sessions/<conversation id>`, not in the shared `/config/workspace`. Files a chat left in the shared directory stay there but are not the working directory.
- Add workspace profiles, set by `WORKSPACE_PROFILES`. A profile lists mounts and says whether its commands carry the GitHub token. A mount is a shallow git clone of `owner/repo`, or a directory shared across sessions, each read-only or read-write.
- A turn uses the `default` profile. Unconfigured, it has no mounts and the GitHub token, as before.
- Read-only is advisory: the sandbox user has sudo, so it stops accidents, not a determined agent. Per-session pods are the way to real isolation and are left for a later change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-tools`: `run_command` runs in the conversation's workspace, built from its profile, and the GitHub token is exported only when the profile allows it.

## Impact

- Code: `agent/workspace.py`, `agent/sandbox.py`, `agent/tools.py`, `agent/deps.py`, `config.py`, the CLI wiring, and tests.
- Operators: new optional `WORKSPACE_PROFILES` (chart value `sandbox.profiles`). With it unset the only change is the working directory.
- Out of scope: per-session pods or containers, per-conversation profile choice from the UI, and cleanup of old workspace directories.
