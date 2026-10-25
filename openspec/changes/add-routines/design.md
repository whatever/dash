## Context

Dash starts work from `dash:jobs`: `chat` jobs from the web UI and `update` jobs from `dash scrape`, a Kubernetes CronJob that runs every 5 minutes. The worker already runs a periodic sweep (every 60 seconds) that expires old approvals. The proposed agent engine (#37) runs a turn in the worker with a tool policy, and the proposed inbox (#39) holds approvals and messages and parks a turn that needs an answer.

Claude Code has three schedulers. The one that fits here is its in-session one: the agent calls `CronCreate` or `ScheduleWakeup`, tasks fire between turns, a session holds at most 50, recurring ones expire after 7 days, a missed run fires once, and jitter spreads load. Its cloud version is human-created, runs at most hourly, and its docs say a stored prompt "can't act as approval or consent for actions during the run". This design borrows those rules.

## Decisions

**The clock is the worker's sweep, not a new CronJob.** The sweep already exists and runs in every worker. Each pass claims due routines in one statement that also sets the next run time, using `FOR UPDATE SKIP LOCKED`, so two workers can't both take the same one. The finest grain is the sweep interval, so a routine is on time to within about a minute. `dash scrape` keeps its own CronJob.

**A fire is a job, and its id comes from the routine and the scheduled time.** The job has kind `routine` and carries the routine id and the time it was due. The id is a hash of both, and the queue's existing seen-key check drops a second enqueue. This also covers the case the webhook PR (#26) flags, where `CLAIM_IDLE_MS` can re-run a job after a worker restart: a re-run is the same job, not a new one.

**Each run is a new conversation.** It matches how a Claude Code run is a session you can open, and how #26 makes a conversation per review. A standing conversation per routine would let a run see the last one, but every run's context would grow and a bad run would poison the next. Facts that should carry over go through the memory tools. The conversation records its routine id, so the UI can group runs.

**Unattended means parked, not blocked.** Nobody watches a fired run. A tool that needs approval defers, the approval waits in the inbox, and the turn resumes when answered or the approval expires. The run isn't a held process. How much a routine may do without asking is the chat modes question (#41). Until then a run follows the tool policy, so `auto` tools run and `ask` tools park.

**A fire is not consent.** It never answers or pre-answers an approval. "Allow always" rules still apply, since a person made them.

**Creation by the agent is an approval, always.** `schedule_routine` is `ask`, and the card shows the full prompt, the schedule and the conversation that proposed it. An "Allow always" rule can't cover it, because the call's arguments are a new prompt every time. This is the same agent-proposes, person-approves pattern as #43.

**A fired run can't create routines.** Without this, one routine could schedule more, each approved once. It can still list and cancel.

**Limits for agent-created routines.** A 15-minute floor (a person can go to 5, the same as sources), at most 20 enabled at once, and an expiry 7 days after creation for recurring ones. After expiry a routine stops firing and stays listed, and a person can renew it. This differs from Claude Code, which fires once more and deletes the task, because a deleted routine can't be renewed. One-shots and person-created routines don't expire.

**Time zones are stored.** Claude Code's session cron uses local time and its cloud cron uses UTC unless told otherwise, which surprises people. Each routine stores an IANA zone, defaulting to a setting, and the UI shows next run in it.

**A missed run fires once.** If the worker was down, one run happens when it returns, and the next run is computed from then. A routine whose previous run is still going skips the fire and moves on, like a CronJob with `concurrencyPolicy: Forbid`.

**Results go to the inbox.** A run that writes only into a conversation nobody opens hasn't told anyone anything. By default the reply, or the error, becomes an inbox message titled with the routine's name. A routine can turn that off.

**`labels` is stored and unused.** An object of free-form labels on the routine. Nothing reads it yet. It is there so a later router can attach budgets by label ("no research this week, grooming is fine") without a migration. The `routine` job kind is likewise the one a router would call an event source.

## Alternatives considered

- **A CronJob per routine, or one that polls a table.** A CronJob tick is 5 minutes at best, adds a pod to the cycle, and has its own failure modes. The sweep exists and is in the process that runs the agent.
- **An in-memory scheduler in the API process.** Lost on restart, duplicated with two replicas.
- **Human-created only, as on today's main.** Useful, but the agent can't act on its own clock. Main also runs chat in hermes, which has none of dash's tools, so the agent can't call anything there.

## Open questions

- **Chat modes.** Should a routine carry a mode (#41), so grooming runs in `auto` and a routine that touches repositories runs in `manual`? Left out here because the modes aren't built.
- **Sources.** `dash scrape` sources are scheduled work too: a kind, a target, an interval and a last-checked time. Should they become a kind of routine, so one panel and one set of tools cover both? That would migrate the sources table and rewrite the `sources` spec. A separate change (`add-source-tools`) gives the agent tools over the sources as they are today.
- **Noise.** One inbox message per run is right for a daily routine and too much for one every 15 minutes. Is the on/off switch enough, or should a routine notify only when something changed?
- **Floor and cap.** 15 minutes and 20 are guesses. Claude Code uses 1 minute in a session and 1 hour in the cloud, and 50 tasks per session.
- **A late one-shot.** If the worker is down for days, should a one-shot still fire when it returns? This draft says yes, once.
- **A self-paced wake-up.** Claude Code also lets the agent pick "wake me in N minutes" each turn. Here that is `schedule_routine` with a one-time schedule, but a dedicated tool that targets the same conversation might be better. Leave it until the first version is used.
- **Router.** The router proposals make a fire an event with a source, a recipe and an engine. This design keeps the job kind and the labels so that move is a rename. Whether to wait for the router before building is a call for the maintainer.
