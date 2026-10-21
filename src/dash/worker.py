"""Consumes `dash:jobs`.

`chat` jobs recall memories, run an agent turn, stream it and store new memories.
`update` jobs (from `dash scrape`) store a real-world item as a memory.
"""

import asyncio
import contextlib
import logging
import socket
import uuid
from collections.abc import Mapping
from typing import Any, Protocol

from pydantic_ai import CancellationToken, Conversation
from redis.exceptions import RedisError

from dash.agent import Delta, Turn, history
from dash.agent.engine import OnDelta
from dash.db import Store
from dash.memory import (
    DUPLICATE_DISTANCE,
    RELEVANT_DISTANCE,
    Embedder,
    Extractor,
    system_prompt,
)
from dash.queue import UPDATE, Job, Queue
from dash.sources.common import Item

log = logging.getLogger(__name__)

# Coalesce deltas so a fast model doesn't write one Redis entry per token.
FLUSH_CHARS = 48
RETRY_SECONDS = 2
STOP_POLL_SECONDS = 0.5


def record(log: list[dict[str, Any]], kind: str, data: Mapping[str, Any]) -> None:
    """Append an event, merging runs of text or reasoning into one entry."""
    if kind in ("delta", "reasoning") and log and log[-1]["kind"] == kind:
        log[-1]["text"] += data.get("text", "")
    else:
        log.append({"kind": kind, **data})


class AgentRunner(Protocol):
    async def run(
        self,
        conversation: Conversation,
        prompt: str,
        *,
        instructions: str | None,
        on_delta: OnDelta,
        cancel: CancellationToken,
    ) -> Turn: ...


class Worker:
    def __init__(
        self,
        *,
        store: Store,
        queue: Queue,
        agent: AgentRunner,
        embedder: Embedder,
        extractor: Extractor,
        top_k: int,
    ) -> None:
        self.store = store
        self.queue = queue
        self.agent = agent
        self.embedder = embedder
        self.extractor = extractor
        self.top_k = top_k
        self.name = f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}"

    async def recall(self, text: str) -> list[str]:
        try:
            embedding = await self.embedder.embed(text)
            hits = await self.store.search_memories(embedding, self.top_k)
        except Exception:
            log.exception("memory recall failed")
            return []
        return [m.content for m, dist in hits if dist <= RELEVANT_DISTANCE]

    async def remember(self, user: str, assistant: str) -> int:
        stored = 0
        try:
            for fact in await self.extractor.extract(user, assistant):
                embedding = await self.embedder.embed(fact)
                nearest = await self.store.search_memories(embedding, 1)
                if nearest and nearest[0][1] < DUPLICATE_DISTANCE:
                    continue
                await self.store.add_memory(fact, embedding, source="conversation")
                stored += 1
        except Exception:
            log.exception("memory extraction failed")
        return stored

    async def handle(self, job: Job) -> None:
        # Every inbound job lands on the LIVE timeline before it runs.
        data = {"conversation_id": job.conversation_id} if job.conversation_id else job.data
        await self.store.add_timeline(job.job_id, job.kind, data)
        if job.kind == UPDATE:
            await self.handle_update(job)
            return
        await self.handle_chat(job)

    async def handle_update(self, job: Job) -> None:
        item = Item.from_dict(job.data)
        text = item.text()
        embedding = await self.embedder.embed(text)
        nearest = await self.store.search_memories(embedding, 1)
        if nearest and nearest[0][1] < DUPLICATE_DISTANCE:
            await self.queue.emit(job.job_id, "done", stored=False)
            return
        source_kind = item.source.split(":", 1)[0]
        await self.store.add_memory(
            text, embedding, source="scrape", tags=[source_kind, item.source]
        )
        await self.queue.emit(job.job_id, "done", stored=True)
        log.info("stored update from %s: %s", item.source, item.title)

    async def conversation(
        self, conversation_id: uuid.UUID, earlier: list[tuple[str, str]]
    ) -> Conversation:
        """Return the stored turn history, or one seeded from the given earlier messages."""
        stored = await self.store.turn_history(conversation_id)
        return history.load(stored) if stored else history.seed(earlier)

    async def watch_stop(self, job_id: str, cancel: CancellationToken) -> None:
        """Cancel the turn once someone asks to stop the given job."""
        while True:
            try:
                if await self.queue.stop_requested(job_id):
                    cancel.cancel()
                    return
            except RedisError:
                log.exception("stop check failed for job %s", job_id)
            await asyncio.sleep(STOP_POLL_SECONDS)

    async def handle_chat(self, job: Job) -> None:
        conversation_id = uuid.UUID(job.conversation_id)
        messages = await self.store.messages(conversation_id)
        if not messages or messages[-1].role != "user":
            await self.queue.emit(job.job_id, "error", message="No user message to answer.")
            return
        user_text = messages[-1].content
        # Everything the UI is shown, in order, so the reply can be rebuilt after a reload.
        trail: list[dict[str, Any]] = []

        async def emit(kind: str, **data: Any) -> None:
            await self.queue.emit(job.job_id, kind, **data)
            record(trail, kind, data)

        memories = await self.recall(user_text)
        if memories:
            await emit("memories", items=memories)

        conversation = await self.conversation(
            conversation_id, [(m.role, m.content) for m in messages[:-1]]
        )

        reply: list[str] = []
        buffers = {"text": "", "reasoning": ""}
        events = {"text": "delta", "reasoning": "reasoning"}

        async def flush(kind: str) -> None:
            if buffers[kind]:
                await emit(events[kind], text=buffers[kind])
                buffers[kind] = ""

        async def on_delta(delta: Delta) -> None:
            if delta.kind in buffers:
                other = "reasoning" if delta.kind == "text" else "text"
                await flush(other)
                if delta.kind == "text":
                    reply.append(delta.text)
                buffers[delta.kind] += delta.text
                if len(buffers[delta.kind]) >= FLUSH_CHARS:
                    await flush(delta.kind)
            else:
                await flush("reasoning")
                await flush("text")
                await emit(delta.kind, **delta.data)

        cancel = CancellationToken()
        watcher = asyncio.create_task(self.watch_stop(job.job_id, cancel))
        try:
            turn = await self.agent.run(
                conversation,
                user_text,
                instructions=system_prompt(memories),
                on_delta=on_delta,
                cancel=cancel,
            )
        except Exception as ex:
            log.exception("agent turn failed")
            await self.queue.emit(job.job_id, "error", message=f"agent: {ex}")
            return
        finally:
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher
        await flush("reasoning")
        await flush("text")

        text = "".join(reply)
        message = await self.store.add_message(conversation_id, "assistant", text, trail)
        await self.store.save_turn_history(conversation_id, history.dump(turn.conversation))
        done: dict[str, Any] = {"message_id": message.id}
        if turn.stopped:
            done["stopped"] = True
        await self.queue.emit(job.job_id, "done", **done)
        if turn.stopped:
            return
        stored = await self.remember(user_text, text)
        if stored:
            log.info("stored %d new memories", stored)

    async def run(self, stop: asyncio.Event | None = None) -> None:
        await self.queue.ensure_group()
        log.info("worker %s waiting for jobs", self.name)
        while not (stop and stop.is_set()):
            try:
                job = await self.queue.claim(self.name)
            except RedisError:
                log.exception("queue unavailable, retrying")
                await asyncio.sleep(RETRY_SECONDS)
                continue
            if job is None:
                continue
            try:
                await self.handle(job)
            except Exception as ex:
                log.exception("job %s failed", job.job_id)
                await self.queue.emit(job.job_id, "error", message=str(ex))
            await self.queue.ack(job)
