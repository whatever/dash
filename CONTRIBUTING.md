# Contributing

Agents and humans follow the same rules. AGENTS.md has the coding and PR rules; this file says who has to approve what.

## Size

- Aim for under 400 changed lines. Over 1000, the automated reviewer skips the PR and asks for a split.
- One concern per PR. Stack large work.

## Review

Every non-draft PR gets an automated review from dash. It posts comments, never approvals, and stops after 3 rounds. The `review:force` label reviews again or reviews an oversized PR.

## Risk tiers

| Tier | Paths | Needs |
| :- | :- | :- |
| Low | `openspec/`, `*.md`, `src/dash/static/` | Green checks and the dash review |
| Normal | Everything else | One human approval |
| High | `charts/`, `Dockerfile`, `.github/`, `src/dash/github/`, `src/dash/webhook.py`, `src/dash/migrations/`, agent tools and sandbox | Approval from a code owner |

CODEOWNERS enforces the high tier through branch protection.
