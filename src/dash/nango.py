"""Thin client for the self-hosted Nango API. Nango holds the OAuth tokens; dash never does."""

from typing import Any, cast

import httpx

# Single-user assistant: every connection belongs to one Nango end user.
END_USER_ID = "owner"


class Nango:
    def __init__(self, base_url: str, secret_key: str) -> None:
        self.enabled = bool(secret_key)
        self._client = httpx.AsyncClient(
            base_url=base_url, headers={"Authorization": f"Bearer {secret_key}"}, timeout=15
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = await self._client.request(method, path, **kwargs)
        response.raise_for_status()
        return cast("dict[str, Any]", response.json()) if response.content else {}

    async def integrations(self) -> list[dict[str, Any]]:
        data = await self._json("GET", "/integrations")
        return cast("list[dict[str, Any]]", data.get("data", []))

    async def connections(self) -> list[dict[str, Any]]:
        data = await self._json("GET", "/connection")
        return cast("list[dict[str, Any]]", data.get("connections", []))

    async def connect_session(self) -> str:
        """A short-lived token the browser hands to Nango Connect UI."""
        data = await self._json("POST", "/connect/sessions", json={"end_user": {"id": END_USER_ID}})
        return str(data["data"]["token"])

    async def delete_connection(self, connection_id: str, provider_config_key: str) -> None:
        await self._json(
            "DELETE",
            f"/connection/{connection_id}",
            params={"provider_config_key": provider_config_key},
        )
