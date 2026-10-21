"""Redis streams job queue.

`dash:jobs` holds one entry per job, read by the `workers` consumer group. A job's
`kind` is `chat` (answer a conversation's last user turn) or `update` (a
real-world item from `dash scrape` to remember).
Each job also gets its own `dash:events:<job>` stream. The worker appends deltas
there and the API replays it to the browser over SSE, so a page reload mid-reply
picks up from the start.
"""

import contextlib
import hashlib
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from redis.asyncio import Redis
from redis.exceptions import ResponseError

JOBS = "dash:jobs"
GROUP = "workers"
EVENTS_TTL_SECONDS = 3600
# A job a dead worker held this long goes to another worker.
CLAIM_IDLE_MS = 5 * 60 * 1000
# Must stay above the longest XREAD block below.
SOCKET_TIMEOUT_SECONDS = 30
# How long `dash scrape` remembers an item it already enqueued.
SEEN_TTL_SECONDS = 30 * 24 * 3600
CHAT = "chat"
UPDATE = "update"


def events_key(job_id: str) -> str:
    return f"dash:events:{job_id}"


def stop_key(job_id: str) -> str:
    return f"dash:stop:{job_id}"


class Keyed(Protocol):
    @property
    def source(self) -> str: ...
    @property
    def key(self) -> str: ...


def seen_key(item: Keyed) -> str:
    digest = hashlib.sha256(f"{item.source}\0{item.key}".encode()).hexdigest()
    return f"dash:seen:{digest}"


@dataclass(frozen=True)
class Job:
    entry_id: str
    job_id: str
    conversation_id: str = ""
    kind: str = CHAT
    data: dict[str, Any] = field(default_factory=dict[str, Any])


class Queue:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    @classmethod
    def from_url(cls, url: str) -> "Queue":
        # redis-py defaults to a 5 s socket timeout, which kills blocking XREADs early.
        return cls(
            Redis.from_url(url, decode_responses=True, socket_timeout=SOCKET_TIMEOUT_SECONDS)  # pyright: ignore[reportUnknownMemberType]
        )

    async def close(self) -> None:
        await self.redis.aclose()

    async def enqueue(self, conversation_id: str) -> str:
        job_id = uuid.uuid4().hex
        await self.redis.xadd(
            JOBS, {"job_id": job_id, "kind": CHAT, "conversation_id": conversation_id}
        )
        return job_id

    async def enqueue_update(self, item: dict[str, Any]) -> str:
        job_id = uuid.uuid4().hex
        await self.redis.xadd(JOBS, {"job_id": job_id, "kind": UPDATE, "data": json.dumps(item)})
        return job_id

    async def seen(self, item: Keyed) -> bool:
        return bool(await self.redis.exists(seen_key(item)))

    async def mark_seen(self, item: Keyed) -> bool:
        """Record an item; False if it was already recorded."""
        return bool(await self.redis.set(seen_key(item), "1", nx=True, ex=SEEN_TTL_SECONDS))

    async def ensure_group(self) -> None:
        try:
            await self.redis.xgroup_create(JOBS, GROUP, id="0", mkstream=True)
        except ResponseError as ex:
            if "BUSYGROUP" not in str(ex):
                raise

    async def claim(self, consumer: str, block_ms: int = 5000) -> Job | None:
        """Next job for this consumer: first any abandoned one, then a new one."""
        claimed: list[Any] = await self.redis.xautoclaim(
            JOBS, GROUP, consumer, CLAIM_IDLE_MS, "0-0", count=1
        )
        entries = cast("list[tuple[str, dict[str, str]]]", claimed[1])
        if not entries:
            read = cast(
                "list[tuple[str, list[tuple[str, dict[str, str]]]]] | None",
                await self.redis.xreadgroup(GROUP, consumer, {JOBS: ">"}, count=1, block=block_ms),
            )
            entries = read[0][1] if read else []
        if not entries:
            return None
        entry_id, fields = entries[0]
        return Job(
            entry_id,
            fields["job_id"],
            fields.get("conversation_id", ""),
            # Entries from before job kinds are chat turns.
            fields.get("kind", CHAT),
            json.loads(fields.get("data", "{}")),
        )

    async def ack(self, job: Job) -> None:
        await self.redis.xack(JOBS, GROUP, job.entry_id)
        await self.redis.xdel(JOBS, job.entry_id)

    async def request_stop(self, job_id: str) -> None:
        """Ask the worker running the given job to stop it."""
        await self.redis.set(stop_key(job_id), "1", ex=EVENTS_TTL_SECONDS)

    async def stop_requested(self, job_id: str) -> bool:
        """Return True if someone asked to stop the given job."""
        return bool(await self.redis.exists(stop_key(job_id)))

    async def emit(self, job_id: str, kind: str, **data: object) -> None:
        key = events_key(job_id)
        await self.redis.xadd(key, {"kind": kind, "data": json.dumps(data)})
        await self.redis.expire(key, EVENTS_TTL_SECONDS)

    async def events(self, job_id: str, block_ms: int = 15000) -> AsyncIterator[dict[str, Any]]:
        """Replay then follow a job's events until `done` or `error`."""
        key = events_key(job_id)
        last = "0"
        while True:
            read = cast(
                "list[tuple[str, list[tuple[str, dict[str, str]]]]] | None",
                await self.redis.xread({key: last}, block=block_ms),
            )
            if not read:
                yield {"kind": "ping"}
                continue
            for entry_id, fields in read[0][1]:
                last = entry_id
                event = {"kind": fields["kind"], **json.loads(fields["data"])}
                yield event
                if event["kind"] in ("done", "error"):
                    return

    async def status(self) -> dict[str, int]:
        waiting = int(await self.redis.xlen(JOBS))
        try:
            pending: dict[str, Any] = await self.redis.xpending(JOBS, GROUP)
            in_flight = int(pending["pending"])
        except ResponseError:
            in_flight = 0
        consumers = 0
        with contextlib.suppress(ResponseError):
            consumers = len(cast("list[Any]", await self.redis.xinfo_consumers(JOBS, GROUP)))
        return {"waiting": waiting - in_flight, "in_flight": in_flight, "workers": consumers}
