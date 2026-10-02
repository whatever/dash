from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dash.db import Authorization
from dash.github.api import Installation, NewApp

PROVIDER = "github"
APP = "app"
INSTALLATION = "installation"


class GitHubStore:
    """GitHub Apps and their installations in the authorizations table."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._session = sessions

    async def _list(self, kind: str) -> Sequence[Authorization]:
        """Return every GitHub authorization of the given kind."""
        async with self._session() as session:
            rows = await session.scalars(
                select(Authorization)
                .where(Authorization.provider == PROVIDER, Authorization.kind == kind)
                .order_by(Authorization.id)
            )
            return rows.all()

    async def apps(self) -> Sequence[Authorization]:
        """Return every stored GitHub App."""
        return await self._list(APP)

    async def installations(self) -> Sequence[Authorization]:
        """Return every stored GitHub App installation."""
        return await self._list(INSTALLATION)

    async def save_app(self, app: NewApp) -> Authorization:
        """Insert or update the given GitHub App and return its row."""
        values: dict[str, Any] = {
            "provider": PROVIDER,
            "kind": APP,
            "external_id": str(app.id),
            "account": app.owner,
            "details": {
                "slug": app.slug,
                "name": app.name,
                "html_url": app.html_url,
                "client_id": app.client_id,
            },
            "secrets": {
                "pem": app.pem,
                "client_secret": app.client_secret,
                **({"webhook_secret": app.webhook_secret} if app.webhook_secret else {}),
            },
        }
        statement = (
            insert(Authorization)
            .values(values)
            .on_conflict_do_update(
                index_elements=["provider", "kind", "external_id"],
                set_={key: values[key] for key in ("account", "details", "secrets")},
            )
            .returning(Authorization)
        )
        async with self._session() as session, session.begin():
            return (await session.scalars(statement)).one()

    async def save_installations(
        self, app: Authorization, installations: Sequence[Installation]
    ) -> None:
        """Replace the stored installations of the given app with the given list."""
        ids = [str(installation.id) for installation in installations]
        async with self._session() as session, session.begin():
            await session.execute(
                delete(Authorization).where(
                    Authorization.parent_id == app.id, Authorization.external_id.not_in(ids)
                )
            )
            if not installations:
                return
            statement = insert(Authorization).values(
                [
                    {
                        "provider": PROVIDER,
                        "kind": INSTALLATION,
                        "external_id": str(installation.id),
                        "parent_id": app.id,
                        "account": installation.account,
                        "details": {
                            "html_url": installation.html_url,
                            "repository_selection": installation.repository_selection,
                        },
                        "secrets": {},
                    }
                    for installation in installations
                ]
            )
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=["provider", "kind", "external_id"],
                    set_={
                        "parent_id": statement.excluded.parent_id,
                        "account": statement.excluded.account,
                        "details": statement.excluded.details,
                    },
                )
            )

    async def delete_app(self, app_id: int) -> bool:
        """Delete the given GitHub App and its installations. Return True if it existed."""
        async with self._session() as session, session.begin():
            result = await session.execute(
                delete(Authorization).where(
                    Authorization.id == app_id,
                    Authorization.provider == PROVIDER,
                    Authorization.kind == APP,
                )
            )
            return bool(cast("CursorResult[Any]", result).rowcount)
