from dash.github.api import installation_client
from dash.github.db import GitHubStore


class NoInstallationError(LookupError):
    pass


class GitHubReviewer:
    def __init__(self, store: GitHubStore) -> None:
        self._store = store

    async def post(self, repo: str, number: int, head_sha: str, body: str) -> str:
        owner, name = repo.split("/", 1)
        apps = {app.id: app for app in await self._store.apps()}
        installation = next(
            (
                i
                for i in await self._store.installations()
                if i.account.lower() == owner.lower() and i.parent_id in apps
            ),
            None,
        )
        if installation is None or installation.parent_id is None:
            raise NoInstallationError(f"No GitHub App installation for {owner}.")
        github = installation_client(apps[installation.parent_id], installation)
        response = await github.rest.pulls.async_create_review(
            owner, name, number, commit_id=head_sha, body=body, event="COMMENT"
        )
        return response.parsed_data.html_url
