## 1. Endpoint

- [ ] 1.1 Add a cheap ping to the store and the queue. Verify: unit tests for success, failure and a hung call.
- [ ] 1.2 Add `GET /readyz` returning 200 or 503 per the spec. Verify: API tests for all three scenarios, and that `/healthz` stays 200 with both dependencies down.

## 2. Chart

- [ ] 2.1 Point the API readiness probe at `/readyz` and leave liveness on `/healthz`. Verify: `helm template` shows the two paths, and stopping Redis marks the pod unready without restarting it.

## 3. Docs

- [ ] 3.1 Note both endpoints in the README. Verify: README lists what each one means.
