## 1. Lease

- [x] 1.1 Renew a running job's claim every 30 seconds, and give a job without renewal to another worker after two minutes. Verify: tests that a long job is not taken while renewed, that a job from a crashed worker is taken after two minutes, and that a failed renewal does not stop the job; and a check on a real Redis.
- [x] 1.2 Stop a job that runs past `JOB_TIMEOUT_SECONDS`, emit an error event and acknowledge it. Verify: a test with a handler that never returns.
- [x] 1.3 Log how long each job took, and warn above five minutes. Verify: a test of the log line.

## 2. Workers

- [x] 2.1 Count only workers active in the last minute. Verify: tests with a live and a stale consumer, and no group.
- [x] 2.2 Delete consumers idle for an hour that hold no entries. Verify: tests that a stale one is deleted and one with an entry is kept.
