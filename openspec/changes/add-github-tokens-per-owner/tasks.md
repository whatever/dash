## 1. Refresher

- [ ] 1.1 List installations (all pages) and mint one token per account into `owners/<account>/token`, keeping a file on a failed mint and removing it when a successful listing drops the account. Verify: script tests against a stubbed GitHub API for two installations, a new one, a removed one, a failed mint and a second page.
- [ ] 1.2 Write the default and fallback tokens per the spec, and run on the fallback alone with no app Secret. Verify: script tests for an id set, an id unset, and fallback only.

## 2. Credentials in the shell

- [ ] 2.1 Add the git credential helper and set `credential.useHttpPath` for `https://github.com` in the seeded `.gitconfig`. Verify: tests that feed the helper git's credential protocol for an installed owner, an uninstalled owner with and without a fallback, and another host.
- [ ] 2.2 Add the `gh` wrapper and link `/usr/local/bin/gh` to it. Verify: tests for `--repo`, `GH_REPO`, an `api repos/…` path, an `origin` remote, and no owner.

## 3. Chart and docs

- [ ] 3.1 Add `sandbox.github.fallbackSecret`, mount it into the refresher only, and make `GITHUB_APP_INSTALLATION_ID` optional. Verify: `helm template` renders with and without each Secret, and the sshd container mounts no key.
- [ ] 3.2 Document installing the app on more than one account and moving from a personal access token to the fallback. Verify: README covers both.
- [ ] 3.3 Run it in a real sandbox with two installations: clone from one owner, push a branch and open a pull request on the other. Verify: both succeed, and the pull request shows the app as its author.
