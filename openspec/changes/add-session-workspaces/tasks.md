## 1. Workspace profiles

- [x] 1.1 Parse and validate `WORKSPACE_PROFILES` into profiles of git and shared mounts. Verify: unit tests for valid profiles and for paths, sources and refs that could escape.
- [x] 1.2 Build the idempotent setup script for a session. Verify: tests run it in a local shell for read-write, read-only and git mounts, twice.

## 2. Use them

- [x] 2.1 Run `run_command` in `/config/workspace/sessions/<conversation id>` with the turn's profile. Verify: the ssh command line names the session directory, and two sessions get two directories.
- [x] 2.2 Export the GitHub token only for profiles that allow it. Verify: a `github: false` profile's command line has no token export.
- [x] 2.3 Bound setup separately from the command. Verify: a hung connection is still killed.

## 3. Operators

- [x] 3.1 Add `sandbox.profiles` to the chart and `WORKSPACE_PROFILES` to compose. Verify: `helm template` renders the variable.
- [ ] 3.2 Try a profile with a git mount and a shared mount against the real sandbox image. Verify: `run_command ls` in a new conversation lists the mounts, and a read-only file refuses a write.
