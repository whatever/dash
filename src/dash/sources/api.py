from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from dash.db import DataSource
from dash.router import Action
from dash.sources.common import Source
from dash.sources.db import SourceStore
from dash.sources.inputs import KINDS

MIN_MINUTES = 5
MAX_MINUTES = 60 * 24 * 7

SourceRoute = Literal[Action.FLAG, Action.IGNORE, Action.REMEMBER]


class NewSource(BaseModel):
    """A source to check and how often to check it."""

    kind: str = Field(pattern=f"^({'|'.join(KINDS)})$")
    target: str = Field(min_length=1, max_length=2000)
    every_minutes: int = Field(default=60, ge=MIN_MINUTES, le=MAX_MINUTES)
    route: SourceRoute | None = None


class SourceChange(BaseModel):
    """The fields of a source that the user can change."""

    enabled: bool | None = None
    every_minutes: int | None = Field(default=None, ge=MIN_MINUTES, le=MAX_MINUTES)
    route: SourceRoute | None = None


def source_json(row: DataSource) -> dict[str, Any]:
    """Return the public fields of a source."""
    return {
        "id": row.id,
        "kind": row.kind,
        "target": row.target,
        "every_minutes": row.every_minutes,
        "enabled": row.enabled,
        "checked_at": row.checked_at.isoformat() if row.checked_at else None,
        "route": row.route,
    }


def create_router(*, store: SourceStore) -> APIRouter:
    """Return the routes that list, add, change, and delete data sources."""
    router = APIRouter(prefix="/api/sources", tags=["sources"])

    @router.get("")
    async def sources() -> list[dict[str, Any]]:
        return [source_json(row) for row in await store.sources()]

    @router.post("", status_code=201)
    async def add(body: NewSource) -> dict[str, Any]:
        if body.kind == "web" and not body.target.startswith(("http://", "https://")):
            raise HTTPException(422, "A web source needs an http:// or https:// URL.")
        return source_json(
            await store.add(Source(body.kind, body.target), body.every_minutes, body.route)
        )

    @router.patch("/{source_id}")
    async def change(source_id: int, body: SourceChange) -> dict[str, Any]:
        values = body.model_dump(mode="json", exclude_none=True)
        if "route" in body.model_fields_set:
            values["route"] = body.route
        row = await store.update(source_id, **values)
        if row is None:
            raise HTTPException(404)
        return source_json(row)

    @router.delete("/{source_id}", status_code=204)
    async def remove(source_id: int) -> None:
        if not await store.delete(source_id):
            raise HTTPException(404)

    return router
