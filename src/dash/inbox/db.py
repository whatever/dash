import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dash.db import InboxItem, ToolRule
from dash.inbox import APPROVAL, DENY, DISMISSED, EXPIRED, MESSAGE, OPEN, RESOLVED, SUPERSEDED

LIST_LIMIT = 100


class InboxStore:
    """Inbox items and the tool rules that "allow always" saves."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._session = sessions

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
        """Open a new item and return it."""
        item = InboxItem(
            kind=kind,
            status=OPEN,
            title=title,
            body=body,
            data=data,
            conversation_id=conversation_id,
            job_id=job_id,
        )
        async with self._session() as session, session.begin():
            session.add(item)
        return item

    async def items(
        self, *, open_only: bool = True, limit: int = LIST_LIMIT
    ) -> Sequence[InboxItem]:
        """Return the newest items, only the open ones unless told otherwise."""
        query = select(InboxItem).order_by(InboxItem.id.desc()).limit(limit)
        if open_only:
            query = query.where(InboxItem.status == OPEN)
        async with self._session() as session:
            return (await session.scalars(query)).all()

    async def count_open(self) -> int:
        """Return the number of open items."""
        query = select(func.count()).select_from(InboxItem).where(InboxItem.status == OPEN)
        async with self._session() as session:
            return int(await session.scalar(query) or 0)

    async def item(self, item_id: int) -> InboxItem | None:
        """Return the given item, if it exists."""
        async with self._session() as session:
            return await session.get(InboxItem, item_id)

    async def resolve(self, item_id: int, decision: str, reason: str = "") -> InboxItem | None:
        """Record the decision on an open approval and return it, or None if it is not one."""
        statement = (
            update(InboxItem)
            .where(InboxItem.id == item_id, InboxItem.kind == APPROVAL, InboxItem.status == OPEN)
            .values(
                status=RESOLVED,
                resolution={"decision": decision, "reason": reason},
                resolved_at=func.now(),
            )
            .returning(InboxItem)
        )
        async with self._session() as session, session.begin():
            return (await session.scalars(statement)).one_or_none()

    async def dismiss(self, item_id: int) -> bool:
        """Dismiss an open message. Return True if there was one."""
        statement = (
            update(InboxItem)
            .where(InboxItem.id == item_id, InboxItem.kind == MESSAGE, InboxItem.status == OPEN)
            .values(status=DISMISSED, resolved_at=func.now())
        )
        async with self._session() as session, session.begin():
            result = await session.execute(statement)
            return bool(cast("CursorResult[Any]", result).rowcount)

    async def open_in_turn(self, job_id: str) -> int:
        """Return the number of approvals from the given turn still waiting for an answer."""
        query = (
            select(func.count())
            .select_from(InboxItem)
            .where(InboxItem.job_id == job_id, InboxItem.kind == APPROVAL, InboxItem.status == OPEN)
        )
        async with self._session() as session:
            return int(await session.scalar(query) or 0)

    async def turn_approvals(self, job_id: str) -> Sequence[InboxItem]:
        """Return every approval the given turn opened."""
        query = select(InboxItem).where(InboxItem.job_id == job_id, InboxItem.kind == APPROVAL)
        async with self._session() as session:
            return (await session.scalars(query.order_by(InboxItem.id))).all()

    async def conversation_approvals(self, conversation_id: uuid.UUID) -> Sequence[InboxItem]:
        """Return every approval the given conversation opened."""
        query = select(InboxItem).where(
            InboxItem.conversation_id == conversation_id, InboxItem.kind == APPROVAL
        )
        async with self._session() as session:
            return (await session.scalars(query.order_by(InboxItem.id))).all()

    async def supersede(self, conversation_id: uuid.UUID) -> int:
        """Deny the conversation's open approvals as superseded. Return how many there were."""
        statement = (
            update(InboxItem)
            .where(
                InboxItem.conversation_id == conversation_id,
                InboxItem.kind == APPROVAL,
                InboxItem.status == OPEN,
            )
            .values(
                status=RESOLVED,
                resolution={"decision": DENY, "reason": SUPERSEDED},
                resolved_at=func.now(),
            )
        )
        async with self._session() as session, session.begin():
            result = await session.execute(statement)
            return int(cast("CursorResult[Any]", result).rowcount)

    async def expire(self, before: datetime) -> int:
        """Expire approvals opened before the given time. Return how many expired."""
        statement = (
            update(InboxItem)
            .where(
                InboxItem.kind == APPROVAL,
                InboxItem.status == OPEN,
                InboxItem.created_at < before,
            )
            .values(status=EXPIRED, resolved_at=func.now())
        )
        async with self._session() as session, session.begin():
            result = await session.execute(statement)
            return int(cast("CursorResult[Any]", result).rowcount)

    async def add_rule(self, tool: str) -> None:
        """Save a rule that lets the given tool run without asking."""
        statement = insert(ToolRule).values(tool=tool, args={}).on_conflict_do_nothing()
        async with self._session() as session, session.begin():
            await session.execute(statement)

    async def rules(self) -> Sequence[ToolRule]:
        """Return every saved rule."""
        async with self._session() as session:
            return (await session.scalars(select(ToolRule).order_by(ToolRule.id))).all()

    async def delete_rule(self, rule_id: int) -> bool:
        """Delete the given rule. Return True if it existed."""
        async with self._session() as session, session.begin():
            result = await session.execute(delete(ToolRule).where(ToolRule.id == rule_id))
            return bool(cast("CursorResult[Any]", result).rowcount)
