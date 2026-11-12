## Context

The sandbox pod's `github-refresher` container holds the app's id and private key from the `dash-github-app` Secret. Every 30 minutes it signs a JWT, mints an installation token for `GITHUB_APP_INSTALLATION_ID` and writes it to `/run/secrets/github/token`. The sshd container never sees the key. Its shell rc exports the token as `GITHUB_TOKEN` before every command, and `.gitconfig` sends git's GitHub credentials through `gh auth git-credential`, which reads that variable.

An installation is one account's grant to the app: a user or organization installs it and picks all or some of its repositories. The app owner sets the permissions; every installation gets the same ones. So an app installed on two accounts has two installations, and each mints its own token, good only for that account's repositories.

## Goals / Non-Goals

**Goals**
- The agent can work on the repositories of every account the app is installed on, in one sandbox, with no choosing.
- A new installation works without a restart or a config change.
- Deployments with one installation see no change.

**Non-Goals**
- Isolating installations from each other inside the sandbox. Every token is readable there; selection is for correctness, not a boundary.
- Per-repository permissions. GitHub does not offer them per installation.
- Using the app the in-app flow stores in Postgres. The sandbox does not reach the database, by design.

## Decisions

**Discover installations instead of listing them.** On each pass the refresher calls `GET /app/installations` with the app JWT and mints a token for each one. A configured list would need a restart for every new installation. `GITHUB_APP_INSTALLATION_ID` keeps one meaning only: which installation is the default.

**One file per account.** Tokens go to `/run/secrets/github/owners/<account>/token`, with the account login lowercased, since GitHub logins are case-insensitive. Each write is a temporary file and a rename, as now. A failed mint keeps the previous file. An account that is missing from a successful listing has its file removed.

**The default.** `/run/secrets/github/token` holds the token for `GITHUB_APP_INSTALLATION_ID` when set, otherwise the app owner's installation, otherwise the fallback. `GITHUB_TOKEN` keeps exporting it, so other tools behave as now.

**git picks by owner through a credential helper.** git passes the repository path to a helper only with `credential.useHttpPath = true`, so `.gitconfig` sets that for `https://github.com` and names a small helper script in place of `gh auth git-credential`. The helper reads the owner from the path and answers `username=x-access-token` with, in order: that owner's token, the fallback, the default. With none it answers nothing, and public repositories still clone anonymously. Mirror fetches for workspace mounts and hubs go through git, so they pick correctly with no change to that code.

**`gh` picks the same way through a wrapper.** The chart links `/usr/local/bin/gh` to a wrapper that works out the owner and sets `GH_TOKEN` for that one call, then runs the real binary. In order, it looks at `-R`/`--repo`, then `GH_REPO`, then an `api` path starting `repos/<owner>/`, then the `origin` remote of the current directory. Otherwise it leaves `GITHUB_TOKEN`, the default, in place.

**The fallback is a Secret, not a replacement refresher.** `sandbox.github.fallbackSecret` names a Secret with a `GITHUB_TOKEN` key, mounted into the refresher and copied to `/run/secrets/github/fallback/token` on each pass. A deployment with no app Secret at all runs on the fallback alone.

## Not chosen

- **The worker choosing a token per conversation.** A conversation's mounts name owners, but the agent's own `git` and `gh` calls do not go through the worker, so they would still need choosing in the sandbox.
- **A list of installation ids in config.** It needs a restart for each new installation.
- **Minting in the worker from the stored app.** It would hand the private key, or fresh tokens, over ssh, and the sandbox is the one place that holds GitHub credentials.

## Risks / Trade-offs

- Every installation's token sits in the sandbox. The agent can use any of them through `run_command`. That reach is narrower than a personal access token's, and each token lasts an hour.
- A push to another account's repository is made as that installation, so it shows as `<app>[bot]` on that repository. The commit author still comes from `.gitconfig`.
- `GET /app/installations` is paginated at 100 per page. The refresher follows pages; an app with many installations costs one mint per installation per pass.

## Open Questions

- Should the default be the app owner's installation even when `GITHUB_APP_INSTALLATION_ID` is set to another one? The proposal keeps the variable as the override.
- Should the wrapper also read `owner/repo` from a bare URL argument (`gh pr view https://github.com/owner/repo/pull/1`)? It is common in agent output.
