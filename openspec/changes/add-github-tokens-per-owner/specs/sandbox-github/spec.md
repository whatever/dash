## ADDED Requirements

### Requirement: The sandbox holds a token for every installation of the app

When the `dash-github-app` Secret is present, the sandbox SHALL, every `INTERVAL_SECONDS`, list the app's installations from GitHub, following every page, and mint an installation token for each. It SHALL write each token to `/run/secrets/github/owners/<account>/token`, with `<account>` the installation's account login in lowercase, replacing the file in one step. `GITHUB_APP_INSTALLATION_ID` SHALL be optional.

#### Scenario: Installed on two accounts

- **WHEN** the app is installed on the accounts `alice` and `Bob`
- **THEN** after one pass, `/run/secrets/github/owners/alice/token` and `/run/secrets/github/owners/bob/token` each hold a token for that installation

#### Scenario: A new installation

- **WHEN** the app is installed on another account while the sandbox is running
- **THEN** that account's token file appears after the next pass, without a restart

#### Scenario: An installation is removed

- **WHEN** a listing succeeds and no longer includes an account that has a token file
- **THEN** that account's token file is removed

#### Scenario: A mint fails

- **WHEN** listing or minting fails for an account that already has a token file
- **THEN** the existing file is kept and the failure is logged

### Requirement: The default token is unchanged for one installation

The sandbox SHALL write a default token to `/run/secrets/github/token`: the token for `GITHUB_APP_INSTALLATION_ID` when it is set, otherwise the token for the installation on the app owner's account, otherwise the fallback token. Commands SHALL keep seeing the default token as `GITHUB_TOKEN`.

#### Scenario: One installation, id set

- **WHEN** the app has one installation and `GITHUB_APP_INSTALLATION_ID` names it
- **THEN** `/run/secrets/github/token` and `GITHUB_TOKEN` hold its token, as before this change

#### Scenario: Id unset

- **WHEN** `GITHUB_APP_INSTALLATION_ID` is unset and the app is installed on its owner's account
- **THEN** the default token is that installation's

### Requirement: git uses the token for the repository's owner

The sandbox's git configuration SHALL send `https://github.com` credential requests, with the repository path, to a helper that answers with username `x-access-token` and, in order of preference, the token for the path's owner, the fallback token, or the default token. When none exists it SHALL answer nothing. It SHALL answer nothing for any other host.

#### Scenario: Two owners in one conversation

- **WHEN** a command clones `alice/notes` and then pushes to `bob/app`
- **THEN** the clone uses alice's installation token and the push uses bob's

#### Scenario: An owner without an installation

- **WHEN** a command fetches `carol/tool` and there is a fallback token
- **THEN** the fallback token is used

#### Scenario: Workspace mirrors

- **WHEN** a conversation mounts repositories from two installed owners
- **THEN** each mirror is fetched with its owner's token

#### Scenario: Another host

- **WHEN** git asks for credentials for a host other than `github.com`
- **THEN** the helper gives none

### Requirement: gh uses the token for the repository it acts on

`gh` in the sandbox SHALL run with the token for the owner of the repository it acts on, taken in order from `-R`/`--repo`, `GH_REPO`, an `api` path beginning `repos/<owner>/`, or the `origin` remote of the current directory, with the same preference as git. When none of these names an owner it SHALL run with the default token.

#### Scenario: A pull request on another account

- **WHEN** a command runs `gh pr create --repo bob/app` with the default token belonging to alice
- **THEN** the pull request is created with bob's installation token

#### Scenario: Inside a clone

- **WHEN** a command runs `gh pr list` in a clone whose `origin` is `https://github.com/bob/app`
- **THEN** it runs with bob's installation token

#### Scenario: Nothing names an owner

- **WHEN** a command runs `gh api user` outside any clone
- **THEN** it runs with the default token

### Requirement: An operator can set a fallback token

When `sandbox.github.fallbackSecret` names a Secret, the sandbox SHALL copy its `GITHUB_TOKEN` to `/run/secrets/github/fallback/token` on every pass. Without the `dash-github-app` Secret, the sandbox SHALL run on the fallback alone, as the default token.

#### Scenario: Fallback only

- **WHEN** there is no app Secret and the fallback Secret holds a personal access token
- **THEN** `GITHUB_TOKEN`, git and gh all use that token

### Requirement: The app's private key stays out of the shell

The app's private key SHALL be readable only by the container that mints tokens. Commands SHALL see installation tokens and the fallback token only.

#### Scenario: A command looks for the key

- **WHEN** a command lists `/run/secrets/github` and the sshd container's mounts
- **THEN** it finds token files and no private key
