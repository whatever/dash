import fakeredis
import pytest

from dash.queue import JOBS, Queue


@pytest.fixture
def queue() -> Queue:
    return Queue(fakeredis.FakeAsyncRedis(decode_responses=True))


async def test_enqueue_claim_ack(queue: Queue) -> None:
    await queue.ensure_group()
    job_id = await queue.enqueue("conv-1")

    job = await queue.claim("w1", block_ms=10)

    assert job is not None
    assert (job.job_id, job.conversation_id) == (job_id, "conv-1")
    assert await queue.status() == {"waiting": 0, "in_flight": 1, "workers": 1}
    await queue.ack(job)
    assert await queue.redis.xlen(JOBS) == 0
    assert await queue.claim("w1", block_ms=10) is None


async def test_ensure_group_twice_is_fine(queue: Queue) -> None:
    await queue.ensure_group()
    await queue.ensure_group()


async def test_events_replay_until_done(queue: Queue) -> None:
    await queue.emit("job", "delta", text="Hel")
    await queue.emit("job", "delta", text="lo")
    await queue.emit("job", "done", message_id=7)
    await queue.emit("job", "delta", text="after done is ignored")

    events = [e async for e in queue.events("job")]

    assert events == [
        {"kind": "delta", "text": "Hel"},
        {"kind": "delta", "text": "lo"},
        {"kind": "done", "message_id": 7},
    ]
    assert 0 < await queue.redis.ttl("dash:events:job") <= 3600
