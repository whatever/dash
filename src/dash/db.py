import uuid
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Self, cast

from alembic import command
from alembic.config import Config
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Text,
    UniqueConstraint,
    delete,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID, insert
from sqlalchemy.engine import CursorResult, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

MIGRATIONS = Path(__file__).parent / "migrations"

# Titan Text Embeddings v2 at its default size. Changing it needs a migration and a re-embed.
EMBED_DIM = 1024


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(Text, default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    # The ordered stream behind an assistant reply: text, reasoning, tool, status, memories.
    events: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TurnHistory(Base):
    """The agent's stored turns for one conversation: messages, usage and pending tool calls."""

    __tablename__ = "turn_history"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    state: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM))
    source: Mapped[str] = mapped_column(Text, default="manual")
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Authorization(Base):
    """A credential set for an external provider, such as a GitHub App or installation."""

    __tablename__ = "authorizations"
    __table_args__ = (UniqueConstraint("provider", "kind", "external_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    provider: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("authorizations.id", ondelete="CASCADE"), index=True
    )
    account: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    secrets: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TimelineEntry(Base):
    """One inbound job, recorded by the worker as it picks the job up."""

    __tablename__ = "timeline"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    job_id: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class DataSource(Base):
    """A source that `dash scrape` checks for updates on a schedule."""

    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("kind", "target"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    target: Mapped[str] = mapped_column(Text)
    every_minutes: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def async_url(url: str) -> str:
    # Most tooling hands out postgresql:// DSNs; SQLAlchemy needs the driver named.
    return make_url(url).set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)


def alembic_config(url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    # Passed via attributes, not set_main_option, so a `%` in the password isn't interpolated.
    config.attributes["url"] = async_url(url)
    return config


def migrate(url: str) -> None:
    """Upgrade to head. Blocking, and runs its own event loop: call via `asyncio.to_thread`."""
    command.upgrade(alembic_config(url), "head")


class Store:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._session = async_sessionmaker(engine, expire_on_commit=False)

    @classmethod
    def from_url(cls, url: str) -> Self:
        # Lazy: no connection is made until the first query.
        return cls(create_async_engine(async_url(url), pool_size=5, pool_pre_ping=True))

    @classmethod
    @asynccontextmanager
    async def connect(cls, url: str) -> AsyncGenerator[Self]:
        store = cls.from_url(url)
        try:
            yield store
        finally:
            await store.close()

    @property
    def sessions(self) -> async_sessionmaker[AsyncSession]:
        """Return the session factory for feature stores that share this engine."""
        return self._session

    async def close(self) -> None:
        await self._engine.dispose()

    async def conversations(self, limit: int = 50) -> Sequence[Conversation]:
        async with self._session() as session:
            rows = await session.scalars(
                select(Conversation).order_by(Conversation.updated_at.desc()).limit(limit)
            )
            return rows.all()

    async def create_conversation(self, title: str | None = None) -> Conversation:
        conversation = Conversation(id=uuid.uuid4(), title=title or "New conversation")
        async with self._session() as session, session.begin():
            session.add(conversation)
        return conversation

    async def conversation(self, conversation_id: uuid.UUID) -> Conversation | None:
        async with self._session() as session:
            return await session.get(Conversation, conversation_id)

    async def delete_conversation(self, conversation_id: uuid.UUID) -> bool:
        """Delete a conversation; its messages go with it via ON DELETE CASCADE."""
        async with self._session() as session, session.begin():
            result = await session.execute(
                delete(Conversation).where(Conversation.id == conversation_id)
            )
            return bool(cast("CursorResult[Any]", result).rowcount)

    async def messages(self, conversation_id: uuid.UUID) -> Sequence[Message]:
        async with self._session() as session:
            rows = await session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.id)
            )
            return rows.all()

    async def add_message(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        events: Sequence[dict[str, Any]] = (),
    ) -> Message:
        message = Message(
            conversation_id=conversation_id, role=role, content=content, events=list(events)
        )
        async with self._session() as session, session.begin():
            session.add(message)
            conversation = await session.get(Conversation, conversation_id)
            if conversation is not None:
                conversation.updated_at = func.now()
                # The first user message names the conversation.
                if role == "user" and conversation.title == "New conversation":
                    conversation.title = content.strip().splitlines()[0][:80] or conversation.title
        return message

    async def turn_history(self, conversation_id: uuid.UUID) -> dict[str, Any] | None:
        """Return the stored turn history of the given conversation, if it has one."""
        async with self._session() as session:
            row = await session.get(TurnHistory, conversation_id)
            return row.state if row else None

    async def save_turn_history(self, conversation_id: uuid.UUID, state: dict[str, Any]) -> None:
        """Store the given turn history for the conversation, replacing any earlier one."""
        statement = insert(TurnHistory).values(conversation_id=conversation_id, state=state)
        statement = statement.on_conflict_do_update(
            index_elements=[TurnHistory.conversation_id],
            set_={"state": statement.excluded.state, "updated_at": func.now()},
        )
        async with self._session() as session, session.begin():
            await session.execute(statement)

    async def memories(self, limit: int = 200) -> Sequence[Memory]:
        async with self._session() as session:
            rows = await session.scalars(
                select(Memory).order_by(Memory.created_at.desc()).limit(limit)
            )
            return rows.all()

    async def search_memories(
        self, embedding: Sequence[float], limit: int
    ) -> list[tuple[Memory, float]]:
        """Nearest memories by cosine distance (0 = same, 2 = opposite)."""
        distance = Memory.embedding.cosine_distance(embedding)
        async with self._session() as session:
            rows = await session.execute(
                select(Memory, distance.label("distance")).order_by(distance).limit(limit)
            )
            return [(memory, float(dist)) for memory, dist in rows.tuples().all()]

    async def add_memory(
        self,
        content: str,
        embedding: Sequence[float],
        source: str = "manual",
        tags: Sequence[str] = (),
    ) -> Memory:
        memory = Memory(content=content, embedding=list(embedding), source=source, tags=list(tags))
        async with self._session() as session, session.begin():
            session.add(memory)
        return memory

    async def add_timeline(self, job_id: str, kind: str, data: dict[str, Any]) -> None:
        async with self._session() as session, session.begin():
            session.add(TimelineEntry(job_id=job_id, kind=kind, data=data))

    async def timeline(self, limit: int = 100) -> Sequence[TimelineEntry]:
        async with self._session() as session:
            rows = await session.scalars(
                select(TimelineEntry).order_by(TimelineEntry.id.desc()).limit(limit)
            )
            return rows.all()

    async def delete_memory(self, memory_id: int) -> bool:
        async with self._session() as session, session.begin():
            result = await session.execute(delete(Memory).where(Memory.id == memory_id))
            return bool(cast("CursorResult[Any]", result).rowcount)


# MCP Server Management Tables


class MCPServer(Base):
    """An approved MCP server that the agent can use."""

    __tablename__ = "mcp_servers"
    __table_args__ = (UniqueConstraint("name", "url"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MCPToolApprovalRequest(Base):
    """A request to approve an MCP server, shown in the inbox."""

    __tablename__ = "mcp_tool_approval_requests"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    mcp_server_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("mcp_servers.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(Text)
    request_context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(Text, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    async def mcp_servers(self, approved_only: bool = False) -> Sequence[MCPServer]:
        """Return all MCP servers, optionally filtered to approved ones."""
        async with self._session() as session:
            query = select(MCPServer)
            if approved_only:
                query = query.where(MCPServer.approved == True)
            rows = await session.scalars(query.order_by(MCPServer.created_at.desc()))
            return rows.all()

    async def get_mcp_server(self, server_id: int) -> MCPServer | None:
        """Return an MCP server by ID."""
        async with self._session() as session:
            return await session.get(MCPServer, server_id)

    async def find_mcp_server(self, name: str, url: str) -> MCPServer | None:
        """Find an MCP server by name and URL."""
        async with self._session() as session:
            row = await session.scalar(
                select(MCPServer).where(MCPServer.name == name, MCPServer.url == url)
            )
            return row

    async def create_or_get_mcp_server(
        self, name: str, url: str, description: str = ""
    ) -> MCPServer:
        """Create or return existing MCP server."""
        existing = await self.find_mcp_server(name, url)
        if existing:
            return existing
        server = MCPServer(name=name, url=url, description=description)
        async with self._session() as session, session.begin():
            session.add(server)
        return server

    async def request_mcp_approval(
        self,
        server_id: int,
        source: str = "agent",
        context: dict[str, Any] | None = None,
    ) -> MCPToolApprovalRequest:
        """Create an approval request for an MCP server."""
        request = MCPToolApprovalRequest(
            mcp_server_id=server_id,
            source=source,
            request_context=context or {},
        )
        async with self._session() as session, session.begin():
            session.add(request)
            server = await session.get(MCPServer, server_id)
            if server is not None:
                server.approval_requested_at = func.now()
        return request

    async def pending_approval_requests(self) -> Sequence[MCPToolApprovalRequest]:
        """Return all pending MCP approval requests."""
        async with self._session() as session:
            rows = await session.scalars(
                select(MCPToolApprovalRequest)
                .where(MCPToolApprovalRequest.status == "pending")
                .order_by(MCPToolApprovalRequest.created_at.desc())
            )
            return rows.all()

    async def approve_mcp_server(self, server_id: int) -> MCPServer | None:
        """Approve an MCP server and mark requests as approved."""
        async with self._session() as session, session.begin():
            server = await session.get(MCPServer, server_id)
            if server is not None:
                server.approved = True
                server.approved_at = func.now()
                # Mark associated requests as approved
                requests = await session.scalars(
                    select(MCPToolApprovalRequest).where(
                        MCPToolApprovalRequest.mcp_server_id == server_id,
                        MCPToolApprovalRequest.status == "pending",
                    )
                )
                for req in requests.all():
                    req.status = "approved"
                    req.resolved_at = func.now()
        return await self.get_mcp_server(server_id)

    async def reject_mcp_server(self, server_id: int) -> MCPServer | None:
        """Reject an MCP server and mark requests as rejected."""
        async with self._session() as session, session.begin():
            server = await session.get(MCPServer, server_id)
            if server is not None:
                await session.execute(
                    delete(MCPServer).where(MCPServer.id == server_id)
                )
                # Mark associated requests as rejected
                requests = await session.scalars(
                    select(MCPToolApprovalRequest).where(
                        MCPToolApprovalRequest.mcp_server_id == server_id,
                        MCPToolApprovalRequest.status == "pending",
                    )
                )
                for req in requests.all():
                    req.status = "rejected"
                    req.resolved_at = func.now()
        return None
