import json
from typing import cast
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dash.db import Authorization
from dash.github import GitHubStore, create_router, installation_client
from dash.github.api import Installation
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
