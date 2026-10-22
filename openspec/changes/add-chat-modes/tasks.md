## 1. Mode on the conversation

- [ ] 1.1 Add a `mode` column to conversations, defaulting to `fast_forward`, with a migration. Verify: the offline migration test renders it, there is a single head, and existing rows read as `fast_forward`.
- [ ] 1.2 Read and change a conversation's mode through the API, rejecting unknown values. Verify: API tests for reading the default, a valid change, and an unknown mode returning 422.

## 2. Approval behaviour

- [ ] 2.1 Make the policy check take the mode: `manual` asks for every call, `fast_forward` keeps today's rules, `dangerously_skip` asks for none, and `never` tools stay hidden in all three. Verify: tests per mode with a tool set to `auto`, `ask` and `never`.
- [ ] 2.2 Apply a mode change from the next turn. Verify: a test that a running turn keeps its mode and the next turn uses the new one.

## 3. Auto and plan

- [ ] 3.1 Add the `auto` classifier behind an interface, with the always-ask list ahead of it and ask on error. Verify: tests with a fake classifier for safe, unsafe, erroring and timing-out verdicts, and a listed call that the classifier cannot approve.
- [ ] 3.2 Add `plan`: withhold side-effect tools until a plan is approved. Verify: a test that a write tool is not offered before approval and is offered after.

## 4. UI

- [ ] 4.1 Add a mode control to the chat, with `dangerously_skip` visibly marked. Verify: on the compose stack, changing the mode changes whether the next call asks.

## 5. Checks

- [ ] 5.1 Run the repo checks. Verify: `uv run ruff check`, `uv run ruff format --check`, `uv run pyright` and `uv run pytest` pass.
- [ ] 5.2 Validate the change. Verify: `openspec validate add-chat-modes --strict` passes.
