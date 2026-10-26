## 1. Decisions and rules

- [ ] 1.1 Add a migration with nullable `action`, `routed_by`, `confidence` and `reason` on `timeline`, and a nullable `route` on `sources`. Verify: the offline migration test renders the columns, and there is a single head.
- [ ] 1.2 Add `dash.router` with the decision types and `route(job, source_route)` running the `rules` and `fallback` stages. Verify: unit tests for chat, a source route, and the fallback.
- [ ] 1.3 Record the decision on the timeline entry, and return it from `/api/live`. Verify: store and API tests, including an entry with no decision.
- [ ] 1.4 Make `Worker.handle` route each job after recording it, and make `handle_update` act on the decision (`ignore`, `remember`, `flag`). Verify: worker tests for each action and for chat.
- [ ] 1.5 Accept, validate and list `route` in the sources API. Verify: API tests for set, clear and an unknown value.

## 2. Model triage

- [ ] 2.1 Add a `Triager` protocol and a Bedrock implementation on `EXTRACT_MODEL`, with fenced item text and a JSON reply. Verify: parsing tests for a valid reply, malformed JSON and an unknown action.
- [ ] 2.2 Add the `model` stage behind `ROUTER_TRIAGE`, with the `ROUTER_MIN_CONFIDENCE` fallback. Verify: tests with a fake triager for each action, low confidence, a timeout and an injection-style item.

## 3. Eval and Live

- [ ] 3.1 Add `dash eval-router <file>`, plus a starter fixture of labelled items that includes an injection case. Verify: a test with a fake triager checks the printed counts and that nothing is stored.
- [ ] 3.2 Show each entry's decision in Live: action, highlighted flags, dimmed ignores, and the reason. Verify: manual check in the local stack.
