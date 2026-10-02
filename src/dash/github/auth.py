import json
import secrets
from collections.abc import Sequence
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from githubkit.exception import GitHubException
from pydantic import BaseModel, Field

from dash.db import Authorization
from dash.github.api import Api
from dash.github.db import GitHubStore

STATE_COOKIE = "github_manifest_state"
STATE_MAX_AGE = 600
PERMISSIONS = {
    "metadata": "read",
    "contents": "read",
    "issues": "write",
    "pull_requests": "write",
}


class NewManifest(BaseModel):
    """The options for a new GitHub App manifest."""

    name: str = Field(default="dash", min_length=1, max_length=34)
    org: str | None = Field(default=None, pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")


def app_json(app: Authorization, installations: Sequence[Authorization]) -> dict[str, Any]:
    """Return the public fields of a GitHub App and its installations."""
    return {
        "id": app.id,
        "app_id": int(app.external_id),
        "owner": app.account,
        "slug": app.details["slug"],
        "name": app.details["name"],
        "html_url": app.details["html_url"],
        "installations": [
            {
                "id": int(installation.external_id),
                "account": installation.account,
                "html_url": installation.details["html_url"],
            }
            for installation in installations
            if installation.parent_id == app.id
        ],
    }


def create_router(*, store: GitHubStore, api: Api, public_url: str = "") -> APIRouter:
    """Return the routes that create, install, and list GitHub Apps."""
    router = APIRouter(tags=["github"])

    def base_url(request: Request) -> str:
        """Return the browser-facing address of dash."""
        return public_url or str(request.base_url).rstrip("/")

    async def sync() -> None:
        """Copy the installations of every stored app from GitHub."""
        try:
            for app in await store.apps():
                await store.save_installations(app, await api.installations(app))
        except GitHubException as ex:
            raise HTTPException(502, f"GitHub: {ex}") from ex

    @router.get("/api/github")
    async def status() -> dict[str, Any]:
        installations = await store.installations()
        return {"apps": [app_json(app, installations) for app in await store.apps()]}

    @router.post("/api/github/manifest")
    async def manifest(body: NewManifest, request: Request, response: Response) -> dict[str, str]:
        state = secrets.token_urlsafe(32)
        base = base_url(request)
        settings = f"organizations/{body.org}/settings" if body.org else "settings"
        response.set_cookie(
            STATE_COOKIE,
            state,
            max_age=STATE_MAX_AGE,
            path="/github",
            httponly=True,
            samesite="lax",
            secure=base.startswith("https://"),
        )
        return {
            "action": f"https://github.com/{settings}/apps/new?state={state}",
            "manifest": json.dumps(
                {
                    "name": body.name,
                    "url": base,
                    "redirect_url": f"{base}/github/callback",
                    "setup_url": f"{base}/github/setup",
                    "setup_on_update": True,
                    "public": False,
                    "default_permissions": PERMISSIONS,
                    "default_events": [],
                }
            ),
        }

    @router.get("/github/callback")
    async def callback(
        code: Annotated[str, Query(pattern=r"^[\w-]{1,128}$")],
        state: str,
        expected: Annotated[str | None, Cookie(alias=STATE_COOKIE)] = None,
    ) -> RedirectResponse:
        if not expected or not secrets.compare_digest(state, expected):
            raise HTTPException(400, "The state does not match. Start again from dash.")
        try:
            new = await api.convert_manifest(code)
        except GitHubException as ex:
            raise HTTPException(502, f"GitHub: {ex}") from ex
        await store.save_app(new)
        response = RedirectResponse(f"{new.html_url}/installations/new", 303)
        response.delete_cookie(STATE_COOKIE, path="/github")
        return response

    @router.get("/github/setup")
    async def setup() -> RedirectResponse:
        await sync()
        return RedirectResponse("/#apps", 303)

    @router.post("/api/github/sync")
    async def sync_now() -> dict[str, Any]:
        await sync()
        return await status()

    @router.delete("/api/github/apps/{app_id}", status_code=204)
    async def forget(app_id: int) -> None:
        if not await store.delete_app(app_id):
            raise HTTPException(404, "No such GitHub App.")

    return router
