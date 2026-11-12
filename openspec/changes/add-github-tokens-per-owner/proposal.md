## Why

The sandbox gets one GitHub token, minted for the one installation named by `GITHUB_APP_INSTALLATION_ID`. An installation belongs to one account, so the agent can only reach one owner's repositories. An operator whose dash works on their own repositories and also on a repository someone else owns, who has installed the operator's app on it, cannot give the agent both. Today the only way around it is to replace the refresher with a classic personal access token, which never expires and acts as the person rather than as dash.

## What Changes

- The refresher lists the app's installations on every pass and mints a token for each, one file per account. `GITHUB_APP_INSTALLATION_ID` becomes optional. When it is set, that installation's token is still the default token, as now.
- git in the sandbox gets its credentials from a helper that hands over the token for the repository's owner. Clones, mirror fetches, hub mounts and pushes pick the right installation without being told.
- `gh` picks the same way, from `--repo`, `GH_REPO`, an `api repos/<owner>/…` path, or the current repository's `origin`.
- An optional fallback token, from a Secret the chart names, is used for owners with no installation. A personal access token goes there instead of replacing the refresher.
- Installing the app on another account takes effect on the next pass, with no restart.
- A deployment with one installation and `GITHUB_APP_INSTALLATION_ID` set behaves as it does now. Nothing is **BREAKING**.

## Capabilities

### New Capabilities

- `sandbox-github`: which token the sandbox uses for which repository, how tokens are minted and refreshed, and the fallback.

### Modified Capabilities

None.

## Impact

- Code: `charts/dash/files/github_refresher.sh`, a git credential helper and a `gh` wrapper shipped with the sandbox, the rc and `.gitconfig` the sandbox's seed step writes, chart values, and tests for the scripts.
- Operators: install the app on each account dash should reach. A deployment that patched the refresher to copy a personal access token can drop the patch and set `sandbox.github.fallbackSecret`.
- Out of scope: minting from the app stored by the in-app flow (the sandbox keeps its own copy of the key in a Secret), different permissions per repository (GitHub sets permissions per app, not per installation), and a token chosen per conversation.
