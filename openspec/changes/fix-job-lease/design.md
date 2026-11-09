## Context

`Queue.claim` hands out a job's entry and, when none is new, takes any entry whose last delivery is older than a limit. An entry is removed only by `ack`, after the handler returns. A job therefore has one clock, "time since delivered", and nothing resets it while the work goes on.

## Decisions

**Renew the claim, don't lengthen the limit.** Any fixed limit is wrong for some job: too short and a long job runs twice, too long and a dead worker's job waits. Renewing every 30 seconds with `XCLAIM` for the worker's own consumer resets the entry's idle time without handing it to anyone, so the limit only has to cover a missed renewal or two. It is two minutes.
- Alternative: a longer idle limit. It delays the retry of a job from a dead worker and still fails for a job longer than the limit.

**A lease needs a deadline.** A renewing worker keeps a hung job claimed forever. The worker stops a job that runs past `JOB_TIMEOUT_SECONDS`, tells whoever is reading its events, and acknowledges it. It does not retry: a job that ran for 30 minutes and hung would do so again.
- Alternative: no deadline, relying on the person to press Stop. Unattended work, such as a scheduled job, has no one to press it.

**A worker is live if it was active in the last minute.** A worker polls at least every five seconds, and a renewing worker resets its idle time on every renewal, so a worker busy with a long job still counts. The queue deletes consumers that have been idle for an hour and hold no entries, so restarts stop adding to the count.

**Timing is logged.** Nothing records how long a job takes. A log line per job, and a warning above five minutes, will show whether the limit is right.

## Risks / Trade-offs

- A renewal that arrives after another worker has taken the job takes it back. Two minutes against 30 seconds makes this unlikely, and the entry is not owned by a name, so it is not checked.
- A job stopped by the deadline may leave work half done outside the queue, such as a review already posted. The deadline is a last resort.
