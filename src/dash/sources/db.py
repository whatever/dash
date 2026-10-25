from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dash.db import DataSource
from dash.sources.common import Source


def is_due(row: DataSource, now: datetime) -> bool:
    """Return True if the given source is enabled and its interval has passed."""
    return row.enabled and (
        row.checked_at is None or row.checked_at + timedelta(minutes=row.every_minutes) <= now
    )


class SourceStore:
    """Data sources that the user configures in the Data panel."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._session = sessions

    async def sources(self) -> Sequence[DataSource]:
        """Return every stored source."""
        async with self._session() as session:
            return (await session.scalars(select(DataSource).order_by(DataSource.id))).all()

    async def due(self, now: datetime) -> list[DataSource]:
        """Return the sources that are due for a check at the given time."""
        return [row for row in await self.sources() if is_due(row, now)]

    async def add(self, source: Source, every_minutes: int, route: str | None = None) -> DataSource:
        """Insert or update the given source and return its row."""
        changes: dict[str, Any] = {
            "every_minutes": every_minutes,
            "enabled": True,
            **({"route": route} if route else {}),
        }
        statement = (
            insert(DataSource)
            .values({"kind": source.kind, "target": source.target, "route": route, **changes})
            .on_conflict_do_update(index_elements=["kind", "target"], set_=changes)
            .returning(DataSource)
        )
        async with self._session() as session, session.begin():
            return (await session.scalars(statement)).one()

    async def update(self, source_id: int, **values: Any) -> DataSource | None:
        """Change the given fields of a source and return its row."""
        if not values:
            async with self._session() as session:
                return await session.get(DataSource, source_id)
        async with self._session() as session, session.begin():
            return (
                await session.scalars(
                    update(DataSource)
                    .where(DataSource.id == source_id)
                    .values(values)
                    .returning(DataSource)
                )
            ).one_or_none()

    async def mark_checked(self, source_ids: Sequence[int], now: datetime) -> None:
        """Record that the given sources were checked at the given time."""
        if not source_ids:
            return
        async with self._session() as session, session.begin():
            await session.execute(
                update(DataSource).where(DataSource.id.in_(source_ids)).values(checked_at=now)
            )

    async def delete(self, source_id: int) -> bool:
        """Delete the given source. Return True if it existed."""
        async with self._session() as session, session.begin():
            result = await session.execute(delete(DataSource).where(DataSource.id == source_id))
            return bool(cast("CursorResult[Any]", result).rowcount)
