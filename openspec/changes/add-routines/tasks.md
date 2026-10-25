## 1. Storage and firing

- [ ] 1.1 Migration: `routines` table, and a nullable routine id on conversations
- [ ] 1.2 A claim statement that selects due routines with `SKIP LOCKED` and sets the next run in the same transaction
- [ ] 1.3 A sweep step that claims, skips routines still running, and enqueues a `routine` job with an id from the routine and the due time
- [ ] 1.4 Worker handling: create the conversation, run the agent turn, leave the inbox message on success or failure

## 2. API and UI

- [ ] 2.1 Routes to list, create, change, delete and run a routine, with the validation in the spec
- [ ] 2.2 A Routines view: next and last run, owner, expiry, pause, run now, renew, delete
- [ ] 2.3 Show the routine's name on the conversations it started

## 3. Agent tools

- [ ] 3.1 `schedule_routine`, `list_routines` and `cancel_routine`
- [ ] 3.2 Always ask for `schedule_routine`, and exclude it from rules saved by "Allow always"
- [ ] 3.3 Leave `schedule_routine` out of the tools offered to a run started by a routine
- [ ] 3.4 Enforce the floor, the cap and the 7-day expiry for agent-created routines

## 4. Tests

- [ ] 4.1 Two workers sweeping at once start a due routine once
- [ ] 4.2 A re-enqueue of the same fire is dropped
- [ ] 4.3 A missed run fires once, and a running routine skips its next fire
- [ ] 4.4 A fired run that needs approval parks in the inbox and resumes after an answer
- [ ] 4.5 Time zone handling across a daylight-saving change
