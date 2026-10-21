import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any, cast

import fakeredis
import pytest
from pydantic_ai import UsageLimits
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaThinkingPart, DeltaToolCall
from pydantic_ai.toolsets import FunctionToolset
from redis.exceptions import TimeoutError as RedisTimeoutError

from dash.agent import history
from dash.db import Store
from dash.queue import Job, Queue
from dash.worker import Worker
from tests.fakes import Chunk, FakeEmbedder, FakeExtractor, FakeStore, ScriptedModel


def terminal_tools() -> FunctionToolset[None]:
    tools = FunctionToolset[None]()

    @tools.tool_plain
    def terminal(command: str) -> str:
        """Run a command."""
        return f"ran {command}"

    return tools


async def setup(
    model: ScriptedModel,
    facts: list[str],
    *,
    tools: FunctionToolset[None] | None = None,
    limits: UsageLimits | None = None,
) -> tuple[Worker, FakeStore, Queue, uuid.UUID, Job]:
    store = FakeStore()
    queue = Queue(fakeredis.FakeAsyncRedis(decode_responses=True))
    worker = Worker(
        store=cast("Store", store),
        queue=queue,
        agent=model.engine([tools] if tools else [], limits),
        embedder=FakeEmbedder(),
        extractor=FakeExtractor(facts),
        top_k=8,
    )
    conv = await store.create_conversation()
    await store.add_message(conv.id, "user", "what do I like?")
    return worker, store, queue, conv.id, Job("1-0", "job", str(conv.id))


async def events(queue: Queue, job_id: str = "job") -> list[dict[str, Any]]:
    return [e async for e in queue.events(job_id)]


def prompts(messages: list[ModelMessage]) -> list[str]:
    return [
        str(part.content)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart)
    ]


async def test_reply_is_streamed_saved_and_memories_learned() -> None:
    model = ScriptedModel(["You like ", "tea."])
    worker, store, queue, conv_id, job = await setup(model, ["The user likes tea."])
    await store.add_memory("what do I like?", await FakeEmbedder().embed("what do I like?"))

    await worker.handle(job)

    got = await events(queue)
    assert got[0] == {"kind": "memories", "items": ["what do I like?"]}
    assert "".join(e["text"] for e in got if e["kind"] == "delta") == "You like tea."
    assert got[-1]["kind"] == "done"
    assert [m.content for m in await store.messages(conv_id)][-1] == "You like tea."
    assert "what do I like?" in (model.infos[0].instructions or "")
    assert [m.content for m in store.mems][-1] == "The user likes tea."
    assert conv_id in store.histories


async def test_reasoning_and_tool_progress_are_streamed_in_order() -> None:
    model = ScriptedModel(
        [
            {0: DeltaThinkingPart(content="Let me look.")},
            {1: DeltaToolCall(name="terminal", json_args='{"command": "ls"}', tool_call_id="c1")},
        ],
        ["Two files."],
    )
    worker, store, queue, conv_id, job = await setup(model, [], tools=terminal_tools())

    await worker.handle(job)

    got = [e for e in await events(queue) if e["kind"] != "done"]
    assert got == [
        {"kind": "reasoning", "text": "Let me look."},
        {
            "kind": "tool",
            "tool": "terminal",
            "label": "ls",
            "toolCallId": "c1",
            "status": "running",
        },
        {"kind": "tool", "tool": "terminal", "toolCallId": "c1", "status": "completed"},
        {"kind": "delta", "text": "Two files."},
    ]
    saved = (await store.messages(conv_id))[-1]
    assert saved.content == "Two files."
    assert saved.events == got


async def test_saved_events_merge_text_runs() -> None:
    model = ScriptedModel(
        ["a" * 40, "b" * 40, {1: DeltaToolCall(name="terminal", json_args='{"command": "x"}')}],
        ["c"],
    )
    worker, store, _, conv_id, job = await setup(model, [], tools=terminal_tools())

    await worker.handle(job)

    saved = (await store.messages(conv_id))[-1]
    assert [e["kind"] for e in saved.events] == ["delta", "tool", "tool", "delta"]
    assert saved.events[0] == {"kind": "delta", "text": "a" * 40 + "b" * 40}
    assert saved.events[-1] == {"kind": "delta", "text": "c"}


async def test_text_is_sent_exactly_once() -> None:
    model = ScriptedModel(["Hello", " there", ", friend."])
    worker, _, queue, _, job = await setup(model, [])

    await worker.handle(job)

    got = await events(queue)
    assert "".join(e["text"] for e in got if e["kind"] == "delta") == "Hello there, friend."


async def test_duplicate_fact_is_not_stored_twice() -> None:
    worker, store, _, _, job = await setup(ScriptedModel(["ok"]), ["The user likes tea."])
    await store.add_memory("The user likes tea.", await FakeEmbedder().embed("The user likes tea."))

    await worker.handle(job)

    assert [m.content for m in store.mems] == ["The user likes tea."]


async def test_agent_failure_reports_error_and_saves_nothing() -> None:
    worker, store, queue, conv_id, job = await setup(ScriptedModel(["partial"], fail=True), [])

    await worker.handle(job)

    got = await events(queue)
    assert got[-1] == {"kind": "error", "message": "agent: upstream down"}
    assert [m.role for m in await store.messages(conv_id)] == ["user"]
    assert conv_id not in store.histories


async def test_failed_turn_leaves_history_for_the_next_one() -> None:
    model = ScriptedModel(["first"])
    worker, store, _, conv_id, job = await setup(model, [])
    await worker.handle(job)
    saved = store.histories[conv_id]

    broken: list[Chunk] = ["broken"]
    model.responses, model.fail = [broken], True
    await store.add_message(conv_id, "user", "second")
    await worker.handle(Job("2-0", "job2", str(conv_id)))
    assert store.histories[conv_id] == saved

    model.fail = False
    await store.add_message(conv_id, "user", "third")
    await worker.handle(Job("3-0", "job3", str(conv_id)))
    assert prompts(model.requests[-1]) == ["what do I like?", "third"]


async def test_later_turns_see_earlier_tool_results() -> None:
    model = ScriptedModel(
        [{0: DeltaToolCall(name="terminal", json_args='{"command": "ls"}', tool_call_id="c1")}],
        ["Done."],
        ["Still here."],
    )
    worker, store, _, conv_id, job = await setup(model, [], tools=terminal_tools())
    await worker.handle(job)
    await store.add_message(conv_id, "user", "and now?")

    await worker.handle(Job("2-0", "job2", str(conv_id)))

    returns = [
        part.content
        for message in model.requests[-1]
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]
    assert returns == ["ran ls"]


async def test_memories_are_instructions_for_one_turn_only() -> None:
    model = ScriptedModel(["one"], ["two"])
    worker, store, _, conv_id, job = await setup(model, [])
    await store.add_memory("what do I like?", await FakeEmbedder().embed("what do I like?"))
    await worker.handle(job)
    await store.add_message(conv_id, "user", "unrelated")

    await worker.handle(Job("2-0", "job2", str(conv_id)))

    assert "what do I like?" in (model.infos[0].instructions or "")
    assert "what do I like?" not in (model.infos[1].instructions or "")


async def test_old_conversation_is_seeded_from_messages() -> None:
    model = ScriptedModel(["sure"])
    worker, store, _, conv_id, _ = await setup(model, [])
    await store.add_message(conv_id, "assistant", "You like tea.")
    await store.add_message(conv_id, "user", "and coffee?")

    await worker.handle(Job("2-0", "job2", str(conv_id)))

    sent = model.requests[0]
    assert prompts(sent) == ["what do I like?", "and coffee?"]
    assert isinstance(sent[1], ModelResponse)
    assert sent[1].parts == [TextPart("You like tea.")]
    assert history.load(store.histories[conv_id]).messages[-1].parts == [TextPart("sure")]


async def test_budget_ends_a_runaway_turn() -> None:
    loop: list[Chunk] = [{0: DeltaToolCall(name="terminal", json_args='{"command": "again"}')}]
    model = ScriptedModel(*([loop] * 5))
    worker, store, queue, conv_id, job = await setup(
        model, [], tools=terminal_tools(), limits=UsageLimits(tool_calls_limit=2)
    )

    await worker.handle(job)

    last = (await events(queue))[-1]
    assert last["kind"] == "error"
    assert last["message"].startswith("agent:")
    assert "tool_calls_limit" in last["message"]
    assert conv_id not in store.histories


class SlowModel(ScriptedModel):
    """Streams some text, then waits until the turn is stopped."""

    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()

    async def stream(self, messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[Chunk]:
        """Yield a partial reply, then hang."""
        self.requests.append(list(messages))
        yield "partial "
        self.started.set()
        await asyncio.sleep(30)
        yield "never"


async def test_stop_ends_the_turn_and_keeps_the_partial_reply() -> None:
    model = SlowModel()
    worker, store, queue, conv_id, job = await setup(model, [])
    task = asyncio.create_task(worker.handle(job))
    await model.started.wait()

    await queue.request_stop("job")
    await asyncio.wait_for(task, 5)

    got = await events(queue)
    assert got[-1]["kind"] == "done"
    assert got[-1]["stopped"] is True
    assert (await store.messages(conv_id))[-1].content == "partial "
    assert conv_id in store.histories


async def test_job_without_user_message_errors() -> None:
    worker, store, queue, conv_id, job = await setup(ScriptedModel(["x"]), [])
    await store.add_message(conv_id, "assistant", "already answered")

    await worker.handle(job)

    assert (await events(queue))[-1]["kind"] == "error"


async def test_run_survives_queue_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    worker, _, queue, _, _ = await setup(ScriptedModel(["x"]), [])
    stop = asyncio.Event()
    calls = 0

    async def flaky_claim(consumer: str, block_ms: int = 5000) -> Job | None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RedisTimeoutError("read timed out")
        stop.set()
        return None

    monkeypatch.setattr(queue, "claim", flaky_claim)
    monkeypatch.setattr("dash.worker.RETRY_SECONDS", 0)

    await worker.run(stop)

    assert calls == 2


async def test_every_job_is_recorded_on_the_timeline() -> None:
    worker, store, _, conv_id, job = await setup(ScriptedModel(["ok"]), [])
    await worker.handle(job)
    await worker.handle(Job("2-0", "j2", kind="update", data={"source": "web:x", "title": "T"}))
    await worker.handle(Job("3-0", "j3", str(uuid.uuid4())))  # errors: no user message
    rows = [(r.job_id, r.kind, r.data) for r in await store.timeline()]
    assert rows[1:] == [
        ("j2", "update", {"source": "web:x", "title": "T"}),
        ("job", "chat", {"conversation_id": str(conv_id)}),
    ]
    assert rows[0][:2] == ("j3", "chat")
