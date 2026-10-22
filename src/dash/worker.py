"""Consumes `dash:jobs`.

`chat` jobs recall memories, run an agent turn, stream it and store new memories.
`resume` jobs continue a turn once a person has answered every approval it waited on.
`update` jobs (from `dash scrape`) store a real-world item as a memory.
"""

import asyncio
import contextlib
import logging
import socket
import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from pydantic_ai import CancellationToken, Conversation, DeferredToolResults
from redis.exceptions import RedisError

from dash.agent import Delta, Turn, history
from dash.agent.answers import answers
from dash.agent.deps import TurnDeps
from dash.agent.engine import OnDelta
from dash.db import Store
from dash.inbox import APPROVAL, APPROVAL_HOURS
from dash.inbox.db import InboxStore
from dash.memory import (
    DUPLICATE_DISTANCE,
    RELEVANT_DISTANCE,
    Embedder,
    Extractor,
    system_prompt,
)
from dash.queue import RESUME, UPDATE, Job, Queue
from dash.sources.common import Item

log = logging.getLogger(__name__)

# Coalesce deltas so a fast model doesn't write one Redis entry per token.
FLUSH_CHARS = 48
RETRY_SECONDS = 2
STOP_POLL_SECONDS = 0.5
SWEEP_SECONDS = 60


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
        prompt: str | None,
        *,
        deps: TurnDeps,
        instructions: str | None,
        on_delta: OnDelta,
        cancel: CancellationToken,
        answers: DeferredToolResults | None = None,
    ) -> Turn: ...


class Worker:
    def __init__(
        self,
        *,
        store: Store,
        inbox: InboxStore,
        queue: Queue,
        agent: AgentRunner,
        embedder: Embedder,
        extractor: Extractor,
        top_k: int,
    ) -> None:
        self.store = store
        self.inbox = inbox
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
        data = (
            {"conversation_id": job.conversation_id, **job.data}
            if job.conversation_id
            else job.data
        )
        await self.store.add_timeline(job.job_id, job.kind, data)
        if job.kind == UPDATE:
            await self.handle_update(job)
        elif job.kind == RESUME:
            await self.handle_resume(job)
        else:
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

    async def answers(
        self, conversation_id: uuid.UUID, conversation: Conversation, *, supersede: bool
    ) -> DeferredToolResults | None:
        """Return the decisions on the calls the conversation waits on, if it waits on any.

        With `supersede`, approvals still open are denied first, because a new message came.
        """
        pending = conversation.deferred_tool_requests
        if pending is None or not pending.approvals:
            return None
        if supersede:
            await self.inbox.supersede(conversation_id)
        return answers(pending, await self.inbox.conversation_approvals(conversation_id))

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
        memories = await self.recall(user_text)
        conversation = await self.conversation(
            conversation_id, [(m.role, m.content) for m in messages[:-1]]
        )
        decided = await self.answers(conversation_id, conversation, supersede=True)
        ended = await self.run_turn(
            job, conversation_id, conversation, user_text, memories=memories, decided=decided
        )
        if ended is None or ended[1].stopped or ended[1].waiting:
            return
        stored = await self.remember(user_text, ended[0])
        if stored:
            log.info("stored %d new memories", stored)

    async def handle_resume(self, job: Job) -> None:
        conversation_id = uuid.UUID(job.conversation_id)
        stored = await self.store.turn_history(conversation_id)
        conversation = history.load(stored) if stored else None
        decided = (
            await self.answers(conversation_id, conversation, supersede=False)
            if conversation
            else None
        )
        if conversation is None or decided is None:
            await self.queue.emit(job.job_id, "error", message="Nothing to resume.")
            return
        await self.run_turn(job, conversation_id, conversation, None, decided=decided)

    async def run_turn(
        self,
        job: Job,
        conversation_id: uuid.UUID,
        conversation: Conversation,
        prompt: str | None,
        *,
        memories: list[str] | None = None,
        decided: DeferredToolResults | None = None,
    ) -> tuple[str, Turn] | None:
        """Run, stream and store a turn. Return its reply and how it ended, or None if it failed."""
        # Everything the UI is shown, in order, so the reply can be rebuilt after a reload.
        trail: list[dict[str, Any]] = []

        async def emit(kind: str, **data: Any) -> None:
            await self.queue.emit(job.job_id, kind, **data)
            record(trail, kind, data)

        if memories:
            await emit("memories", items=memories)

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

        approved = frozenset(r.tool for r in await self.inbox.rules())
        deps = TurnDeps(conversation_id, job.job_id, approved)
        cancel = CancellationToken()
        watcher = asyncio.create_task(self.watch_stop(job.job_id, cancel))
        try:
            turn = await self.agent.run(
                conversation,
                prompt,
                deps=deps,
                instructions=system_prompt(memories or []),
                on_delta=on_delta,
                cancel=cancel,
                answers=decided,
            )
        except Exception as ex:
            log.exception("agent turn failed")
            await self.queue.emit(job.job_id, "error", message=f"agent: {ex}")
            return None
        finally:
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher
        await flush("reasoning")
        await flush("text")

        awaiting: list[int] = []
        for call in turn.waiting:
            item = await self.inbox.add(
                kind=APPROVAL,
                title=f"Run {call.tool}?",
                body=call.label,
                data={
                    "tool": call.tool,
                    "args": call.args,
                    "tool_call_id": call.tool_call_id,
                    "label": call.label,
                },
                conversation_id=conversation_id,
                job_id=job.job_id,
            )
            awaiting.append(item.id)
            await emit(
                "approval",
                item_id=item.id,
                conversation_id=str(conversation_id),
                tool=call.tool,
                label=call.label,
                toolCallId=call.tool_call_id,
            )

        text = "".join(reply)
        message = await self.store.add_message(conversation_id, "assistant", text, trail)
        await self.store.save_turn_history(conversation_id, history.dump(turn.conversation))
        done: dict[str, Any] = {"message_id": message.id}
        if turn.stopped:
            done["stopped"] = True
        if awaiting:
            done["awaiting"] = awaiting
        await self.queue.emit(job.job_id, "done", **done)
        return text, turn

    async def sweep(self) -> None:
        """Expire approvals nobody answered in time."""
        before = datetime.now(UTC) - timedelta(hours=APPROVAL_HOURS)
        try:
            expired = await self.inbox.expire(before)
        except Exception:
            log.exception("approval expiry failed")
            return
        if expired:
            log.info("expired %d approvals", expired)

    async def run(self, stop: asyncio.Event | None = None) -> None:
        await self.queue.ensure_group()
        log.info("worker %s waiting for jobs", self.name)
        swept = 0.0
        while not (stop and stop.is_set()):
            if time.monotonic() - swept >= SWEEP_SECONDS:
                await self.sweep()
                swept = time.monotonic()
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
