import asyncio
import uuid
from typing import Any, cast

import fakeredis
import pytest
from redis.exceptions import TimeoutError as RedisTimeoutError

from dash.db import Store
from dash.hermes import Delta
from dash.queue import JOBS, Job, Queue
from dash.worker import Worker
from tests.fakes import FakeChat, FakeEmbedder, FakeExtractor, FakeStore


async def setup(
    chat: FakeChat, facts: list[str]
) -> tuple[Worker, FakeStore, Queue, uuid.UUID, Job]:
    store = FakeStore()
    queue = Queue(fakeredis.FakeAsyncRedis(decode_responses=True))
    worker = Worker(
        store=cast("Store", store),
        queue=queue,
        chat=chat,
        embedder=FakeEmbedder(),
        extractor=FakeExtractor(facts),
        top_k=8,
    )
    conv = await store.create_conversation()
    await store.add_message(conv.id, "user", "what do I like?")
    return worker, store, queue, conv.id, Job("1-0", "job", str(conv.id))


async def events(queue: Queue) -> list[dict[str, Any]]:
    return [e async for e in queue.events("job")]


async def test_reply_is_streamed_saved_and_memories_learned() -> None:
    chat = FakeChat(["You like ", "tea."])
    worker, store, queue, conv_id, job = await setup(chat, ["The user likes tea."])
    await store.add_memory("what do I like?", await FakeEmbedder().embed("what do I like?"))

    await worker.handle(job)

    got = await events(queue)
    assert got[0] == {"kind": "memories", "items": ["what do I like?"]}
    assert "".join(e["text"] for e in got if e["kind"] == "delta") == "You like tea."
    assert got[-1]["kind"] == "done"
    assert [m.content for m in await store.messages(conv_id)][-1] == "You like tea."
    assert chat.seen[0]["conversation"] == f"dash:{conv_id}"
    assert chat.seen[0]["input"] == "what do I like?"
    assert "what do I like?" in (chat.seen[0]["instructions"] or "")
    assert [m.content for m in store.mems][-1] == "The user likes tea."


async def test_reasoning_and_tool_progress_are_streamed_in_order() -> None:
    tool = {"tool": "terminal", "label": "ls", "toolCallId": "c1", "status": "running"}
    chat = FakeChat(
        [
            Delta("reasoning", "Let me look."),
            Delta("tool", data=tool),
            "Two files.",
            Delta("status", data={"message": "ok"}),
        ]
    )
    worker, store, queue, conv_id, job = await setup(chat, [])

    await worker.handle(job)

    got = [e for e in await events(queue) if e["kind"] != "done"]
    assert got == [
        {"kind": "reasoning", "text": "Let me look."},
        {"kind": "tool", **tool},
        {"kind": "delta", "text": "Two files."},
        {"kind": "status", "message": "ok"},
    ]
    saved = (await store.messages(conv_id))[-1]
    assert saved.content == "Two files."
    assert saved.events == got


async def test_saved_events_merge_text_runs() -> None:
    chat = FakeChat(["a" * 40, "b" * 40, Delta("tool", data={"tool": "t"}), "c"])
    worker, store, _, conv_id, job = await setup(chat, [])

    await worker.handle(job)

    saved = (await store.messages(conv_id))[-1]
    assert saved.events == [
        {"kind": "delta", "text": "a" * 40 + "b" * 40},
        {"kind": "tool", "tool": "t"},
        {"kind": "delta", "text": "c"},
    ]


async def test_duplicate_fact_is_not_stored_twice() -> None:
    worker, store, _, _, job = await setup(FakeChat(["ok"]), ["The user likes tea."])
    await store.add_memory("The user likes tea.", await FakeEmbedder().embed("The user likes tea."))

    await worker.handle(job)

    assert [m.content for m in store.mems] == ["The user likes tea."]


async def test_hermes_failure_reports_error_and_saves_nothing() -> None:
    worker, store, queue, conv_id, job = await setup(FakeChat(["partial"], fail=True), [])

    await worker.handle(job)

    got = await events(queue)
    assert got[-1] == {"kind": "error", "message": "hermes: upstream down"}
    assert [m.role for m in await store.messages(conv_id)] == ["user"]


async def test_job_without_user_message_errors() -> None:
    worker, store, queue, conv_id, job = await setup(FakeChat(["x"]), [])
    await store.add_message(conv_id, "assistant", "already answered")

    await worker.handle(job)

    assert (await events(queue))[-1]["kind"] == "error"


async def test_run_survives_queue_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    worker, _, queue, _, _ = await setup(FakeChat(["x"]), [])
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


async def test_conversation_id_is_stable_and_only_new_message_is_sent() -> None:
    chat = FakeChat(["ok"])
    worker, store, _, conv_id, job = await setup(chat, [])
    await worker.handle(job)
    await store.add_message(conv_id, "user", "and now?")
    await worker.handle(Job("2-0", "job2", str(conv_id)))

    assert [s["conversation"] for s in chat.seen] == [f"dash:{conv_id}"] * 2
    assert [s["input"] for s in chat.seen] == ["what do I like?", "and now?"]


async def test_every_job_is_recorded_on_the_timeline() -> None:
    worker, store, _, conv_id, job = await setup(FakeChat(["ok"]), [])
    await worker.handle(job)
    await worker.handle(Job("2-0", "j2", kind="update", data={"source": "web:x", "title": "T"}))
    await worker.handle(Job("3-0", "j3", str(uuid.uuid4())))  # errors: no user message
    rows = [(r.job_id, r.kind, r.data) for r in await store.timeline()]
    assert rows[1:] == [
        ("j2", "update", {"source": "web:x", "title": "T"}),
        ("job", "chat", {"conversation_id": str(conv_id)}),
    ]
    assert rows[0][:2] == ("j3", "chat")


async def run_one_job(worker: Worker, queue: Queue, job_id: str) -> Job:
    await queue.ensure_group()
    await queue.enqueue(job_id)
    job = await queue.claim(worker.name, block_ms=10)
    assert job is not None
    return job


async def test_running_job_is_not_claimed_while_the_lease_renews(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker, _, queue, _, _ = await setup(FakeChat(["x"]), [])
    job = await run_one_job(worker, queue, "conv")
    monkeypatch.setattr("dash.queue.CLAIM_IDLE_MS", 300)
    monkeypatch.setattr("dash.worker.LEASE_RENEW_SECONDS", 0.05)

    async def slow_handle(job: Job) -> None:
        await asyncio.sleep(0.8)

    monkeypatch.setattr(worker, "handle", slow_handle)
    running = asyncio.create_task(worker.process(job))
    stolen: list[Job | None] = []
    for _ in range(8):
        await asyncio.sleep(0.1)
        stolen.append(await queue.claim("other", block_ms=1))
    await running

    assert stolen == [None] * 8
    assert await queue.redis.xlen(JOBS) == 0


async def test_crashed_consumers_job_is_reclaimed_after_the_idle_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker, _, queue, _, _ = await setup(FakeChat(["x"]), [])
    job = await run_one_job(worker, queue, "conv")
    monkeypatch.setattr("dash.queue.CLAIM_IDLE_MS", 100)

    assert await queue.claim("other", block_ms=1) is None
    await asyncio.sleep(0.2)
    reclaimed = await queue.claim("other", block_ms=1)

    assert reclaimed is not None
    assert reclaimed.entry_id == job.entry_id


async def test_failed_renewal_does_not_kill_the_job(monkeypatch: pytest.MonkeyPatch) -> None:
    worker, _, queue, _, _ = await setup(FakeChat(["x"]), [])
    job = await run_one_job(worker, queue, "conv")
    monkeypatch.setattr("dash.worker.LEASE_RENEW_SECONDS", 0.01)
    attempts = 0
    handled = False

    async def broken_renew(consumer: str, job: Job) -> None:
        nonlocal attempts
        attempts += 1
        raise RedisTimeoutError("read timed out")

    async def slow_handle(job: Job) -> None:
        nonlocal handled
        await asyncio.sleep(0.1)
        handled = True

    monkeypatch.setattr(queue, "renew", broken_renew)
    monkeypatch.setattr(worker, "handle", slow_handle)

    await worker.process(job)

    assert attempts > 1
    assert handled
    assert await queue.redis.xlen(JOBS) == 0


async def test_hung_job_times_out_with_an_error_and_is_acked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker, _, queue, _, _ = await setup(FakeChat(["x"]), [])
    worker.turn_timeout_seconds = 0.05
    job = await run_one_job(worker, queue, "conv")
    cancelled = asyncio.Event()

    async def hang(job: Job) -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(worker, "handle", hang)

    await worker.process(Job(job.entry_id, "job", job.conversation_id))

    assert cancelled.is_set()
    assert await events(queue) == [{"kind": "error", "message": "The job timed out."}]
    assert await queue.redis.xlen(JOBS) == 0
    assert (await queue.status())["in_flight"] == 0


async def test_run_prunes_stale_consumers_once_a_minute(monkeypatch: pytest.MonkeyPatch) -> None:
    worker, _, queue, _, _ = await setup(FakeChat(["x"]), [])
    stop = asyncio.Event()
    pruned = 0

    async def prune() -> int:
        nonlocal pruned
        pruned += 1
        return 0

    async def claim(consumer: str, block_ms: int = 5000) -> Job | None:
        if pruned:
            stop.set()
        return None

    monkeypatch.setattr(queue, "prune_consumers", prune)
    monkeypatch.setattr(queue, "claim", claim)

    await worker.run(stop)

    assert pruned == 1
