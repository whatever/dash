from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from dash.db import InboxItem
from dash.inbox import ALLOW_ALWAYS, APPROVAL, OPEN, RESOLVED
from dash.inbox.db import InboxStore
from dash.queue import Queue


class Answer(BaseModel):
    """A person's decision on an approval."""

    decision: Literal["allow", "allow_always", "deny"]


def item_json(item: InboxItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "kind": item.kind,
        "status": item.status,
        "title": item.title,
        "body": item.body,
        "data": item.data,
        "conversation_id": str(item.conversation_id) if item.conversation_id else None,
        "resolution": item.resolution,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
    }


def create_router(*, store: InboxStore, queue: Queue) -> APIRouter:
    router = APIRouter(prefix="/api/inbox")

    @router.get("")
    async def items(status: Literal["open", "all"] = "open") -> list[dict[str, Any]]:
        return [item_json(i) for i in await store.items(open_only=status == "open")]

    @router.get("/count")
    async def count() -> dict[str, int]:
        return {"open": await store.count_open()}

    @router.get("/rules")
    async def rules() -> list[dict[str, Any]]:
        return [{"id": r.id, "tool": r.tool, "args": r.args} for r in await store.rules()]

    @router.get("/{item_id}")
    async def get_item(item_id: int) -> dict[str, Any]:
        item = await store.item(item_id)
        if item is None:
            raise HTTPException(404, "No such item.")
        return item_json(item)

    async def already_resolved(item: InboxItem | None, response: Response) -> dict[str, Any]:
        if item is None or item.kind != APPROVAL or item.status != RESOLVED:
            raise HTTPException(409, "That item is not an approval that can be answered.")
        response.status_code = 200
        job_id = await queue.resume_job(item.job_id)
        return {"resolution": item.resolution, **({"job_id": job_id} if job_id else {})}

    @router.post("/{item_id}/resolve", status_code=202)
    async def resolve(item_id: int, body: Answer, response: Response) -> dict[str, Any]:
        found = await store.item(item_id)
        if found is None:
            raise HTTPException(404, "No such item.")
        if found.kind != APPROVAL or found.status != OPEN:
            return await already_resolved(found, response)
        item = await store.resolve(item_id, body.decision)
        if item is None:
            return await already_resolved(await store.item(item_id), response)
        if body.decision == ALLOW_ALWAYS:
            await store.add_rule(str(item.data["tool"]))
        if await store.open_in_turn(item.job_id) or item.conversation_id is None:
            return {}
        item_ids = [i.id for i in await store.turn_approvals(item.job_id)]
        job_id = await queue.enqueue_resume(item.job_id, str(item.conversation_id), item_ids)
        return {"job_id": job_id} if job_id else {}

    @router.post("/{item_id}/dismiss", status_code=204)
    async def dismiss(item_id: int) -> Response:
        if await store.item(item_id) is None:
            raise HTTPException(404, "No such item.")
        if not await store.dismiss(item_id):
            raise HTTPException(409, "Only an open message can be dismissed.")
        return Response(status_code=204)

    @router.delete("/rules/{rule_id}", status_code=204)
    async def delete_rule(rule_id: int) -> Response:
        if not await store.delete_rule(rule_id):
            raise HTTPException(404, "No such rule.")
        return Response(status_code=204)

    return router
