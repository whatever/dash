## Why

A worker takes a job and acknowledges it only when the job is done. The queue gives any job held unfinished for five minutes to another worker. A job that legitimately runs longer than that, such as a long shell command or many tool calls, looks abandoned, so a second worker (or the same one after a restart) can take it and run it again while the first run is still going. A hung job, on the other hand, is never stopped.

The `workers` figure at `/api/queue` has a separate fault: it counts every consumer the queue has ever seen. Each restart of the worker pod adds one that is never removed, so the number only grows.

## What Changes

- A worker renews its claim on the job it is running every 30 seconds, so a running job is never given to another worker.
- A job held without renewal is given to another worker after two minutes, not five. A worker that dies is replaced sooner.
- A job that runs longer than a limit (30 minutes by default, `JOB_TIMEOUT_SECONDS`) is stopped, its reader is told "The job timed out." and it is not retried.
- The worker logs how long each job took, and warns when one took more than five minutes.
- `/api/queue` counts a worker only while it is active, and the queue forgets consumers that have been idle for an hour and hold nothing.
- Nothing is **BREAKING**.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `chat`: how a job is held and handed over, a limit on how long one may run, and what counts as a worker.

## Impact

- Code: the queue's claim and status, the worker's run loop, the settings, the README.
- Operators: `JOB_TIMEOUT_SECONDS` (default 1800). No chart change.
- Out of scope: retrying a timed-out job, per-kind limits, and a limit on a whole conversation. A conversation has no limit; this bounds one job.
