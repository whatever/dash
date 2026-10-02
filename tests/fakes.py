import itertools
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import UTC, datetime

from dash.db import Conversation, Memory, Message


class FakeStore:
    """In-memory Store. Distance is 0 for an exact text match, else 1."""

    def __init__(self) -> None:
        self.convs: dict[uuid.UUID, Conversation] = {}
        self.msgs: list[Message] = []
        self.mems: list[Memory] = []
        self._ids = itertools.count(1)

    async def conversations(self, limit: int = 50) -> list[Conversation]:
        return list(self.convs.values())[:limit]

    async def create_conversation(self, title: str | None = None) -> Conversation:
        c = Conversation(id=uuid.uuid4(), title=title or "New conversation")
        c.updated_at = datetime.now(UTC)
        self.convs[c.id] = c
        return c

    async def conversation(self, conversation_id: uuid.UUID) -> Conversation | None:
        return self.convs.get(conversation_id)

    async def messages(self, conversation_id: uuid.UUID) -> list[Message]:
        return [m for m in self.msgs if m.conversation_id == conversation_id]

    async def add_message(self, conversation_id: uuid.UUID, role: str, content: str) -> Message:
        m = Message(id=next(self._ids), conversation_id=conversation_id, role=role, content=content)
        self.msgs.append(m)
        return m

    async def memories(self, limit: int = 200) -> list[Memory]:
        return self.mems[:limit]

    async def search_memories(
        self, embedding: Sequence[float], limit: int
    ) -> list[tuple[Memory, float]]:
        hits = [(m, 0.0 if m.embedding == list(embedding) else 1.0) for m in self.mems]
        return sorted(hits, key=lambda h: h[1])[:limit]

    async def add_memory(
        self,
        content: str,
        embedding: Sequence[float],
        source: str = "manual",
        tags: Sequence[str] = (),
    ) -> Memory:
        m = Memory(
            id=next(self._ids),
            content=content,
            embedding=list(embedding),
            source=source,
            tags=list(tags),
            created_at=datetime.now(UTC),
        )
        self.mems.append(m)
        return m

    async def delete_memory(self, memory_id: int) -> bool:
        before = len(self.mems)
        self.mems = [m for m in self.mems if m.id != memory_id]
        return len(self.mems) < before


class FakeEmbedder:
    """Every text gets its own fixed vector, so equal texts are distance 0."""

    async def embed(self, text: str) -> list[float]:
        return [float(len(text)), float(sum(map(ord, text)) % 997)]


class FakeExtractor:
    def __init__(self, facts: list[str]) -> None:
        self.facts = facts

    async def extract(self, user: str, assistant: str) -> list[str]:
        return self.facts


class FakeChat:
    def __init__(self, chunks: list[str], fail: bool = False) -> None:
        self.chunks = chunks
        self.fail = fail
        self.seen: list[list[dict[str, str]]] = []

    async def stream(self, messages: Sequence[Mapping[str, str]]) -> AsyncIterator[str]:
        self.seen.append([dict(m) for m in messages])
        for chunk in self.chunks:
            yield chunk
        if self.fail:
            raise RuntimeError("upstream down")
