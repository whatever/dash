import itertools
import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic_ai import UsageLimits, models
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaThinkingCalls, DeltaToolCalls, FunctionModel
from pydantic_ai.toolsets import AbstractToolset

from dash.agent import Engine, build_agent
from dash.agent.deps import TurnDeps
from dash.agent.mcp import ServerTools
from dash.agent.policy import ToolPolicy
from dash.db import (
    Authorization,
    Conversation,
    DataSource,
    InboxItem,
    Memory,
    Message,
    TimelineEntry,
    ToolRule,
)
from dash.github.api import Installation, NewApp
from dash.github.db import APP, INSTALLATION, PROVIDER
from dash.inbox import APPROVAL, DENY, DISMISSED, EXPIRED, MESSAGE, OPEN, RESOLVED, SUPERSEDED
from dash.sources.common import Source

models.ALLOW_MODEL_REQUESTS = False

Chunk = str | DeltaToolCalls | DeltaThinkingCalls

CLIENT_SECRET = "fake-client-secret"  # noqa: S105


class FakeStore:
    """In-memory Store. Distance is 0 for an exact text match, else 1."""

    def __init__(self) -> None:
        self.convs: dict[uuid.UUID, Conversation] = {}
        self.msgs: list[Message] = []
        self.mems: list[Memory] = []
        self.timeline_rows: list[TimelineEntry] = []
        self.histories: dict[uuid.UUID, dict[str, Any]] = {}
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

    async def delete_conversation(self, conversation_id: uuid.UUID) -> bool:
        if self.convs.pop(conversation_id, None) is None:
            return False
        self.msgs = [m for m in self.msgs if m.conversation_id != conversation_id]
        self.histories.pop(conversation_id, None)
        return True

    async def messages(self, conversation_id: uuid.UUID) -> list[Message]:
        return [m for m in self.msgs if m.conversation_id == conversation_id]

    async def add_message(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        events: Sequence[dict[str, Any]] = (),
    ) -> Message:
        m = Message(
            id=next(self._ids),
            conversation_id=conversation_id,
            role=role,
            content=content,
            events=list(events),
        )
        self.msgs.append(m)
        return m

    async def turn_history(self, conversation_id: uuid.UUID) -> dict[str, Any] | None:
        return self.histories.get(conversation_id)

    async def save_turn_history(self, conversation_id: uuid.UUID, state: dict[str, Any]) -> None:
        self.histories[conversation_id] = state

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

    async def add_timeline(self, job_id: str, kind: str, data: dict[str, Any]) -> None:
        self.timeline_rows.append(
            TimelineEntry(
                id=next(self._ids),
                job_id=job_id,
                kind=kind,
                data=data,
                created_at=datetime.now(UTC),
            )
        )

    async def timeline(self, limit: int = 100) -> list[TimelineEntry]:
        return self.timeline_rows[::-1][:limit]

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


class FakeInboxStore:
    """In-memory InboxStore."""

    def __init__(self) -> None:
        self.rows: list[InboxItem] = []
        self.tool_rules: list[ToolRule] = []
        self._ids = itertools.count(1)

    async def add(
        self,
        *,
        kind: str,
        title: str,
        body: str = "",
        data: dict[str, Any],
        conversation_id: uuid.UUID | None,
        job_id: str,
    ) -> InboxItem:
        item = InboxItem(
            id=next(self._ids),
            kind=kind,
            status=OPEN,
            title=title,
            body=body,
            data=data,
            conversation_id=conversation_id,
            job_id=job_id,
            created_at=datetime.now(UTC),
        )
        self.rows.append(item)
        return item

    async def items(self, *, open_only: bool = True, limit: int = 100) -> list[InboxItem]:
        rows = [r for r in self.rows if r.status == OPEN or not open_only]
        return rows[::-1][:limit]

    async def count_open(self) -> int:
        return sum(r.status == OPEN for r in self.rows)

    async def item(self, item_id: int) -> InboxItem | None:
        return next((r for r in self.rows if r.id == item_id), None)

    def _close(self, item: InboxItem, status: str, resolution: dict[str, Any] | None) -> None:
        item.status, item.resolution, item.resolved_at = status, resolution, datetime.now(UTC)

    async def resolve(self, item_id: int, decision: str, reason: str = "") -> InboxItem | None:
        item = await self.item(item_id)
        if item is None or item.kind != APPROVAL or item.status != OPEN:
            return None
        self._close(item, RESOLVED, {"decision": decision, "reason": reason})
        return item

    async def dismiss(self, item_id: int) -> bool:
        item = await self.item(item_id)
        if item is None or item.kind != MESSAGE or item.status != OPEN:
            return False
        self._close(item, DISMISSED, None)
        return True

    async def open_in_turn(self, job_id: str) -> int:
        return sum(
            r.job_id == job_id and r.kind == APPROVAL and r.status == OPEN for r in self.rows
        )

    async def turn_approvals(self, job_id: str) -> list[InboxItem]:
        return [r for r in self.rows if r.job_id == job_id and r.kind == APPROVAL]

    async def conversation_approvals(self, conversation_id: uuid.UUID) -> list[InboxItem]:
        return [r for r in self.rows if r.conversation_id == conversation_id and r.kind == APPROVAL]

    async def supersede(self, conversation_id: uuid.UUID) -> int:
        open_ones = [
            r for r in await self.conversation_approvals(conversation_id) if r.status == OPEN
        ]
        for item in open_ones:
            self._close(item, RESOLVED, {"decision": DENY, "reason": SUPERSEDED})
        return len(open_ones)

    async def expire(self, before: datetime) -> int:
        old = [
            r
            for r in self.rows
            if r.kind == APPROVAL and r.status == OPEN and r.created_at < before
        ]
        for item in old:
            self._close(item, EXPIRED, None)
        return len(old)

    async def add_rule(self, tool: str) -> None:
        if not any(r.tool == tool for r in self.tool_rules):
            self.tool_rules.append(ToolRule(id=next(self._ids), tool=tool, args={}))

    async def rules(self) -> list[ToolRule]:
        return list(self.tool_rules)

    async def delete_rule(self, rule_id: int) -> bool:
        before = len(self.tool_rules)
        self.tool_rules = [r for r in self.tool_rules if r.id != rule_id]
        return len(self.tool_rules) < before


class ScriptedModel:
    """A model that streams one scripted response per request and records what it was sent."""

    def __init__(self, *responses: list[Chunk], fail: bool = False) -> None:
        self.responses = list(responses)
        self.fail = fail
        self.requests: list[list[ModelMessage]] = []
        self.infos: list[AgentInfo] = []

    async def stream(self, messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[Chunk]:
        """Yield the next scripted response, then fail if told to."""
        self.requests.append(list(messages))
        self.infos.append(info)
        for chunk in self.responses.pop(0) if self.responses else ["ok"]:
            yield chunk
        if self.fail:
            raise RuntimeError("upstream down")

    def engine(
        self,
        toolsets: Sequence[AbstractToolset[TurnDeps]] = (),
        limits: UsageLimits | None = None,
        *,
        policy: ToolPolicy | None = None,
        servers: Sequence[ServerTools] = (),
    ) -> Engine:
        """Return an engine that answers with this model."""
        model = FunctionModel(stream_function=self.stream)
        agent = build_agent(model, toolsets=toolsets, policy=policy)
        return Engine(agent, limits or UsageLimits(), servers=servers, policy=policy)


class FakeGitHubStore:
    """An in-memory GitHubStore."""

    def __init__(self) -> None:
        self.rows: list[Authorization] = []
        self._ids = itertools.count(1)

    async def apps(self) -> list[Authorization]:
        """Return every stored app."""
        return [r for r in self.rows if r.kind == APP]

    async def installations(self) -> list[Authorization]:
        """Return every stored installation."""
        return [r for r in self.rows if r.kind == INSTALLATION]

    async def save_app(self, app: NewApp) -> Authorization:
        """Store the given app and return its row."""
        row = Authorization(
            id=next(self._ids),
            provider=PROVIDER,
            kind=APP,
            external_id=str(app.id),
            account=app.owner,
            details={
                "slug": app.slug,
                "name": app.name,
                "html_url": app.html_url,
                "client_id": app.client_id,
            },
            secrets={"pem": app.pem, "client_secret": app.client_secret},
        )
        self.rows.append(row)
        return row

    async def save_installations(
        self, app: Authorization, installations: Sequence[Installation]
    ) -> None:
        """Replace the installations of the given app."""
        self.rows = [r for r in self.rows if r.parent_id != app.id] + [
            Authorization(
                id=next(self._ids),
                provider=PROVIDER,
                kind=INSTALLATION,
                external_id=str(i.id),
                parent_id=app.id,
                account=i.account,
                details={"html_url": i.html_url},
                secrets={},
            )
            for i in installations
        ]

    async def delete_app(self, app_id: int) -> bool:
        """Delete the given app and its installations. Return True if it existed."""
        before = len(self.rows)
        self.rows = [r for r in self.rows if app_id not in (r.id, r.parent_id)]
        return len(self.rows) < before


class FakeGitHubApi:
    """A GitHub API that returns fixed apps and installations."""

    def __init__(self, installations: list[Installation]) -> None:
        self.installs = installations
        self.codes: list[str] = []

    async def convert_manifest(self, code: str) -> NewApp:
        """Return a fixed new app for the given code."""
        self.codes.append(code)
        return NewApp(
            id=123,
            slug="dash-test",
            name="dash test",
            owner="octocat",
            html_url="https://github.com/apps/dash-test",
            client_id="Iv1.abc",
            client_secret=CLIENT_SECRET,
            webhook_secret=None,
            pem="fake-pem",
        )

    async def installations(self, app: Authorization) -> list[Installation]:
        """Return the fixed installations."""
        return self.installs


class FakeSourceStore:
    """In-memory SourceStore."""

    def __init__(self) -> None:
        self.rows: dict[int, DataSource] = {}
        self._ids = itertools.count(1)

    async def sources(self) -> list[DataSource]:
        return list(self.rows.values())

    async def add(self, source: Source, every_minutes: int) -> DataSource:
        existing = next(
            (r for r in self.rows.values() if (r.kind, r.target) == (source.kind, source.target)),
            None,
        )
        row = existing or DataSource(id=next(self._ids), kind=source.kind, target=source.target)
        row.every_minutes, row.enabled = every_minutes, True
        self.rows[row.id] = row
        return row

    async def update(self, source_id: int, **values: Any) -> DataSource | None:
        row = self.rows.get(source_id)
        for key, value in values.items() if row else ():
            setattr(row, key, value)
        return row

    async def delete(self, source_id: int) -> bool:
        return self.rows.pop(source_id, None) is not None
