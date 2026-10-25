import asyncio
import uuid
from typing import Any, cast

import fakeredis
import pytest
from redis.exceptions import TimeoutError as RedisTimeoutError

from dash.db import Store
from dash.hermes import Delta
from dash.queue import Job, Queue
from dash.router import Action
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


async def test_every_job_records_its_decision() -> None:
    worker, store, _, _, job = await setup(FakeChat(["ok"]), [])
    await worker.handle(job)
    await worker.handle(Job("2-0", "j2", kind="update", data={"source": "web:x", "title": "T"}))
    rows = {r.job_id: (r.action, r.routed_by) for r in await store.timeline()}
    assert rows == {"job": ("chat", "rules"), "j2": ("remember", "fallback")}


async def test_ignored_update_is_not_stored() -> None:
    worker, store, queue, _, _ = await setup(FakeChat([]), [])
    store.routes["web:x"] = Action.IGNORE
    await worker.handle(Job("2-0", "j2", kind="update", data={"source": "web:x", "title": "T"}))
    assert store.mems == []
    assert [e async for e in queue.events("j2")] == [{"kind": "done", "stored": False}]


async def test_flagged_update_is_stored_with_the_flag() -> None:
    worker, store, _, _, _ = await setup(FakeChat([]), [])
    store.routes["web:x"] = Action.FLAG
    await worker.handle(Job("2-0", "j2", kind="update", data={"source": "web:x", "title": "T"}))
    assert [m.tags for m in store.mems] == [["web", "web:x", "flagged"]]
