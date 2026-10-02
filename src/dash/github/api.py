from dataclasses import dataclass
from typing import Protocol

from githubkit import AppAuthStrategy, AppInstallationAuthStrategy, GitHub
from githubkit_schemas.latest.models import Enterprise, SimpleUser

from dash.db import Authorization


@dataclass(frozen=True)
class NewApp:
    """The settings and credentials that GitHub returns for a new app."""

    id: int
    slug: str
    name: str
    owner: str
    html_url: str
    client_id: str
    client_secret: str
    webhook_secret: str | None
    pem: str


@dataclass(frozen=True)
class Installation:
    """An installation of a GitHub App on a user or organization account."""

    id: int
    account: str
    html_url: str
    repository_selection: str


class Api(Protocol):
    """The GitHub calls that the app setup flow makes."""

    async def convert_manifest(self, code: str) -> NewApp: ...

    async def installations(self, app: Authorization) -> list[Installation]: ...


def _login(account: SimpleUser | Enterprise | None) -> str:
    """Return the login or slug of a GitHub account."""
    match account:
        case SimpleUser():
            return account.login
        case Enterprise():
            return account.slug
        case None:
            return ""


def app_client(app: Authorization) -> GitHub[AppAuthStrategy]:
    """Return a client that acts as the given GitHub App."""
    return GitHub(
        AppAuthStrategy(
            app.external_id,
            app.secrets["pem"],
            app.details["client_id"],
            app.secrets["client_secret"],
        )
    )


def installation_client(
    app: Authorization, installation: Authorization
) -> GitHub[AppInstallationAuthStrategy]:
    """Return a client that acts as the given installation of a GitHub App."""
    return GitHub(
        AppInstallationAuthStrategy(
            app.external_id,
            app.secrets["pem"],
            int(installation.external_id),
            app.details["client_id"],
            app.secrets["client_secret"],
        )
    )


class GitHubApi:
    """The GitHub REST API calls for the app setup flow."""

    async def convert_manifest(self, code: str) -> NewApp:
        """Return the new app that GitHub created from a manifest code."""
        response = await GitHub().rest.apps.async_create_from_manifest(code)
        app = response.parsed_data
        return NewApp(
            id=app.id,
            slug=app.slug or str(app.id),
            name=app.name,
            owner=_login(app.owner),
            html_url=app.html_url,
            client_id=app.client_id,
            client_secret=app.client_secret,
            webhook_secret=app.webhook_secret,
            pem=app.pem,
        )

    async def installations(self, app: Authorization) -> list[Installation]:
        """Return every installation of the given GitHub App."""
        github = app_client(app)
        return [
            Installation(
                id=installation.id,
                account=_login(installation.account),
                html_url=installation.html_url,
                repository_selection=installation.repository_selection,
            )
            async for installation in github.paginate(github.rest.apps.async_list_installations)
        ]
