from dash.github.api import Api
from dash.github.db import GitHubStore


class GitHubCredentials:
    """The GitHub env that dash forwards to hermes for one run."""

    def __init__(self, store: GitHubStore, api: Api) -> None:
        self._store = store
        self._api = api

    async def env(self) -> dict[str, str]:
        """Return a new installation token as GITHUB_TOKEN and GH_TOKEN, or nothing."""
        apps = {app.id: app for app in await self._store.apps()}
        installation = next(
            (i for i in await self._store.installations() if i.parent_id in apps), None
        )
        if installation is None or installation.parent_id is None:
            return {}
        token = await self._api.installation_token(apps[installation.parent_id], installation)
        return {"GITHUB_TOKEN": token, "GH_TOKEN": token}
