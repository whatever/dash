## Why

Dash only acts when a person writes to it or when `dash scrape` finds something. The agent can't say "check the build every morning" or "look at this again on Friday" and have it happen. Claude Code can: its agent schedules prompts on a clock, with limits that keep a forgotten schedule from running forever.

This change proposes the same for dash: **routines**, prompts that run on a schedule, created by a person or by the agent. It is a proposal to discuss, not a settled design. The open questions in `design.md` are the ones to answer before building.

## What Changes

- Add routines: a name, a prompt, a schedule (a cron expression or one time), a time zone, an owner (`user` or `agent`) and an on/off switch.
- Each run starts a new conversation named for the routine, so it can be opened and read like any chat.
- A run's reply, or its failure, is left in the inbox so a person hears about it.
- The agent gets `schedule_routine`, `list_routines` and `cancel_routine`. Creating a routine as the agent waits for a person's approval.
- A fired run cannot create routines, and a fire never counts as approval for anything.
- Agent-created recurring routines stop after 7 days unless a person renews them, have a 15-minute floor, and are capped in number.
- A Routines view in the web UI lists them with next and last run, and can pause, run now and delete.
- Nothing is **BREAKING**. Existing chats, sources and `dash scrape` are unchanged.

Out of scope: moving `dash scrape` sources onto routines, choosing a different engine per routine, per-routine approval modes, event or webhook triggers, and any catch-up of missed runs beyond one.

## Capabilities

### New Capabilities

- `routines`: what a routine is, how it fires, what a run does, and the limits on agent-created ones.

### Modified Capabilities

None. This change is written against the agent engine, tools and inbox proposed in whatever/dash#36 to #40, and the chat modes proposed in #41. It refers to their ideas, not their specs, so it can be read and validated on its own. Once they land, the tool and approval requirements here should be reconciled with the `agent-tools` and `inbox` specs.

## Impact

- Code: a `routines` table and a migration, a `routine` job kind, one step in the worker's periodic sweep, three agent tools, a conversation column that records which routine started it, API routes and a Routines view.
- Operators: new settings for the default time zone, the agent-created floor and cap. No new pod or CronJob.
- Security: a routine is the agent writing its own future prompts. If the agent wrote one after reading a web page, that text would run again unattended. Approval at creation, no routines from routines, expiry and the cap bound that, and `design.md` says why.
