## Context

The agent's only filesystem is the `dash-sandbox` pod, reached over ssh as one user in one directory. The sandbox user has sudo, and the pod holds the GitHub token file. Any rule enforced by file modes inside that pod can be undone by the agent.

## Decisions

### A directory per conversation, a profile per kind of session

`TurnDeps` carries a profile name, `default` for chat. The worker never sees paths: `run_command` sends the conversation id and the profile, and the sandbox side builds the directory. Dream and other job kinds can name their own profile later without a new mechanism.

### Set up on every command, not once

The setup script runs before each command and is idempotent: it makes the directory, clones a git mount only when it is missing, links a read-write shared mount only when it is missing, and re-copies a read-only shared mount. Nothing is remembered in the worker, so a restart or a second worker needs no handover. The cost is a few `test` calls per command.

### Mount kinds

- `git`: `git clone --depth 1` of `https://github.com/<owner>/<repo>` at a ref, into a temporary name that is moved into place on success, so a clone that dies leaves no half-checkout. It uses the token only when the profile allows it, so a profile with `github: false` reaches public repositories only.
- `shared`: a directory under `/config/shared/<name>`, created when missing. Read-write links the live directory, so writes reach every session. Read-only is a fresh copy before every command with write bits removed, so a session always reads current content and cannot write back through its copy. It suits small directories such as notes.

### Read-only is advisory

`chmod a-w` on a clone or copy stops `git commit`, an editor or a careless `>` redirect. It does not stop `sudo` or `chmod u+w`. The spec says so, so no one reads a read-only mount as a security boundary.

### Validation at the edge

Profiles are validated when the worker starts. Paths are relative names with no `..`; git sources are `owner/repo`; refs cannot start with `-`; shared sources are one directory name. Everything is shell-quoted as well. A bad profile stops the worker with a validation error rather than at the first command.

### Not chosen: a pod per session

It gives real isolation but needs the worker to create pods (RBAC in the cluster, the docker socket in compose), a lifecycle for them, and a way to mount shared state. The profile and `session`/`profile` arguments are the seam it would plug into.

## Risks

- Existing conversations lose their old working directory. The shared `/config/workspace` is the parent of the session directories, so files there are still reachable by path.
- A first command that has to clone is slow and counts against the setup timeout of 120 seconds, separate from the command's 90.
- Session directories are never removed. They are small until an agent clones something into one.
