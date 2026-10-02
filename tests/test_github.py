import json
from typing import cast
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dash.db import Authorization
from dash.github import GitHubStore, create_router, installation_client
from dash.github.api import GitHubApi, Installation
from dash.github.auth import STATE_COOKIE
from tests.fakes import CLIENT_SECRET, FakeGitHubApi, FakeGitHubStore


@pytest.fixture
def store() -> FakeGitHubStore:
    return FakeGitHubStore()


@pytest.fixture
def api() -> FakeGitHubApi:
    return FakeGitHubApi([Installation(42, "octo-org", "https://github.com/i/42", "all")])


@pytest.fixture
def client(store: FakeGitHubStore, api: FakeGitHubApi) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_router(store=cast("GitHubStore", store), api=api, public_url="https://dash.example")
    )
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


def start(client: TestClient, org: str | None = None) -> tuple[str, dict[str, object]]:
    body: dict[str, str] = client.post("/api/github/manifest", json={"org": org}).json()
    state = parse_qs(urlsplit(body["action"]).query)["state"][0]
    return state, json.loads(body["manifest"])


def test_manifest_prefills_urls_and_sets_state_cookie(client: TestClient) -> None:
    state, manifest = start(client)

    assert client.cookies[STATE_COOKIE] == state
    assert manifest["redirect_url"] == "https://dash.example/github/callback"
    assert manifest["setup_url"] == "https://dash.example/github/setup"
    assert manifest["public"] is False


def test_manifest_for_org(client: TestClient) -> None:
    body = client.post("/api/github/manifest", json={"org": "octo-org"}).json()

    assert body["action"].startswith("https://github.com/organizations/octo-org/settings/apps/new")


def test_manifest_rejects_bad_org(client: TestClient) -> None:
    assert client.post("/api/github/manifest", json={"org": "../x"}).status_code == 422


def test_callback_rejects_wrong_state(client: TestClient, api: FakeGitHubApi) -> None:
    start(client)

    assert client.get("/github/callback", params={"code": "c0de", "state": "x"}).status_code == 400
    assert api.codes == []


def test_create_install_and_list(client: TestClient, store: FakeGitHubStore) -> None:
    state, _ = start(client)

    created = client.get("/github/callback", params={"code": "c0de", "state": state})
    installed = client.get("/github/setup")

    assert created.status_code == 303
    assert created.headers["location"] == "https://github.com/apps/dash-test/installations/new"
    assert installed.headers["location"] == "/#apps"
    [app] = client.get("/api/github").json()["apps"]
    assert app["app_id"] == 123
    assert app["installations"] == [
        {"id": 42, "account": "octo-org", "html_url": "https://github.com/i/42"}
    ]
    assert CLIENT_SECRET not in json.dumps(app)
    assert client.delete(f"/api/github/apps/{app['id']}").status_code == 204
    assert store.rows == []


def test_forget_unknown_app_is_404(client: TestClient) -> None:
    assert client.delete("/api/github/apps/9").status_code == 404


def test_installation_client_uses_stored_ids() -> None:
    app = Authorization(
        id=1,
        external_id="123",
        details={"client_id": "Iv1.abc"},
        secrets={"pem": "fake-pem", "client_secret": CLIENT_SECRET},
    )
    installation = Authorization(id=2, external_id="42", parent_id=1)

    auth = installation_client(app, installation).auth

    assert (auth.app_id, auth.installation_id, auth.client_id) == ("123", 42, "Iv1.abc")


def owner(login: str) -> dict[str, object]:
    url = f"https://api.github.com/users/{login}"
    return {
        "login": login,
        "id": 1,
        "node_id": "U_1",
        "avatar_url": url,
        "gravatar_id": None,
        "url": url,
        "html_url": url,
        "followers_url": url,
        "following_url": url,
        "gists_url": url,
        "starred_url": url,
        "subscriptions_url": url,
        "organizations_url": url,
        "repos_url": url,
        "events_url": url,
        "received_events_url": url,
        "type": "User",
        "site_admin": False,
    }


async def test_convert_manifest_calls_github() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/app-manifests/c0de/conversions"
        return httpx.Response(
            201,
            json={
                "id": 123,
                "slug": "dash-test",
                "node_id": "A_1",
                "client_id": "Iv1.abc",
                "owner": owner("octocat"),
                "name": "dash test",
                "description": None,
                "external_url": "https://dash.example",
                "html_url": "https://github.com/apps/dash-test",
                "created_at": "2026-10-02T00:00:00Z",
                "updated_at": "2026-10-02T00:00:00Z",
                "permissions": {"metadata": "read"},
                "events": [],
                "client_secret": CLIENT_SECRET,
                "webhook_secret": None,
                "pem": "fake-pem",
            },
        )

    new = await GitHubApi(httpx.MockTransport(handler)).convert_manifest("c0de")

    assert (new.id, new.owner, new.client_secret) == (123, "octocat", CLIENT_SECRET)
