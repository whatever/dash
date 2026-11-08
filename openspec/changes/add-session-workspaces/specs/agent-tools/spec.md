## MODIFIED Requirements

### Requirement: The agent can run commands in the sandbox

The agent SHALL have a `run_command` tool. It runs a shell command over SSH in the `dash-sandbox` pod, in a workspace directory of its own for the conversation, `/config/workspace/sessions/<conversation id>`, and returns the exit code and the combined output. Before each command the system SHALL create that directory if it is missing and bring the turn's workspace profile up to date in it. It connects as `SANDBOX_USER` (default `agent`) to `SANDBOX_HOST` and `SANDBOX_PORT` (default 2222). The worker SHALL hold only the SSH key; the Nango and GitHub tokens SHALL stay in the sandbox.

#### Scenario: A command succeeds

- **WHEN** the agent runs `git --version`
- **THEN** the tool returns exit code 0 and the git version printed in the sandbox

#### Scenario: A command fails

- **WHEN** the agent runs a command that exits with status 2
- **THEN** the tool returns exit code 2 and the command's output, and the turn continues

#### Scenario: Two conversations

- **WHEN** the agent writes a file in one conversation and lists its working directory in another
- **THEN** the file is not there

### Requirement: Sandbox commands can use GitHub

Each command SHALL run with `GITHUB_TOKEN` and `GH_TOKEN` set from the sandbox's GitHub token file when it exists and the turn's workspace profile allows GitHub, whether or not the sandbox's login shell reads its rc files. `gh` and `git` over HTTPS SHALL then reach the private repositories the GitHub App can see. The tool SHALL mask any GitHub token in the output before the model sees it. A profile with `github` false SHALL run its commands, and clone its git mounts, without the token.

#### Scenario: A private repository

- **WHEN** the agent runs `gh repo view <private repository the app is installed on>`
- **THEN** the tool returns the repository, and the worker holds no GitHub token

#### Scenario: A command prints the token

- **WHEN** the agent runs `env` and the output contains the GitHub token
- **THEN** the tool returns the output with the token replaced by `***`

#### Scenario: No token file

- **WHEN** the sandbox has no GitHub token file
- **THEN** commands still run, unauthenticated

#### Scenario: A profile without GitHub

- **WHEN** the turn's profile has `github` false and the agent runs `env`
- **THEN** the output holds no `GITHUB_TOKEN` or `GH_TOKEN`

## ADDED Requirements

### Requirement: Workspace profiles say what a session's workspace holds

The system SHALL read named workspace profiles from `WORKSPACE_PROFILES`, a JSON object of profile name to `{github, mounts}`. `github` defaults to true. Each mount has a `kind` (`git` or `shared`), a relative `path` inside the workspace, a `mode` of `ro` (default) or `rw`, and a `source`. A `git` mount's source is `owner/repo` and it may have a `ref`; a `shared` mount's source is one directory name under the sandbox's shared root.

#### Scenario: A git mount

- **WHEN** the `default` profile mounts `acme/app` at `repos/app` read-only and a conversation runs `ls repos/app`
- **THEN** the repository's files are listed, and the clone is made on the first command only

#### Scenario: A shared directory, read-write

- **WHEN** a profile mounts the shared directory `wiki` read-write at `wiki` and a session writes `wiki/a.md`
- **THEN** another session that mounts `wiki` sees `a.md`

#### Scenario: Commands that start together

- **WHEN** the agent issues several commands at once as the first commands of a conversation
- **THEN** the workspace and each mount are set up once, and no mount is created inside another

#### Scenario: A shared directory, read-only

- **WHEN** a profile mounts the shared directory `wiki` read-only and the agent edits `wiki/a.md` with a plain write
- **THEN** the write is refused, and the shared directory is unchanged

### Requirement: A turn uses one profile

A turn SHALL use the profile named `default` unless its job kind names another. A name with no profile, or an unset `WORKSPACE_PROFILES`, SHALL mean no mounts and `github` true.

#### Scenario: Unconfigured

- **WHEN** `WORKSPACE_PROFILES` is unset and a conversation runs a command
- **THEN** it runs in its own empty workspace directory with the GitHub token as before

### Requirement: An invalid profile stops the worker

The system SHALL refuse to start the worker when a profile is invalid. A mount path SHALL be a relative path of plain names, a `git` source SHALL be `owner/repo`, and a `ref` SHALL NOT start with `-`.

#### Scenario: A mount that could escape

- **WHEN** a profile has a mount path of `../x`, an absolute path, a `git` source that is not `owner/repo`, or a ref starting with `-`
- **THEN** the worker does not start and reports the invalid profile

### Requirement: Read-only mounts are a guard against accidents

The system SHALL make a read-only mount refuse ordinary writes, and SHALL NOT present it as a security boundary: the agent can run commands with `sudo` in the sandbox.

#### Scenario: Stated plainly

- **WHEN** an operator reads the `WORKSPACE_PROFILES` documentation
- **THEN** it says read-only mounts stop accidents and do not stop a determined agent
