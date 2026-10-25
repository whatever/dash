from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dash.db import DataSource
from dash.sources.api import create_router
from dash.sources.db import SourceStore, is_due
from tests.fakes import FakeSourceStore

NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(create_router(store=cast("SourceStore", FakeSourceStore())))
    return TestClient(app)


def test_add_pause_and_remove_a_web_source(client: TestClient) -> None:
    added = client.post(
        "/api/sources", json={"kind": "web", "target": "https://n/", "every_minutes": 15}
    ).json()
    assert added == {
        "id": 1,
        "kind": "web",
        "target": "https://n/",
        "every_minutes": 15,
        "enabled": True,
        "checked_at": None,
        "route": None,
    }

    paused = client.patch("/api/sources/1", json={"enabled": False}).json()

    assert paused["enabled"] is False
    assert client.get("/api/sources").json() == [paused]
    assert client.delete("/api/sources/1").status_code == 204
    assert client.get("/api/sources").json() == []


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "rss", "target": "https://n/"},
        {"kind": "web", "target": "ftp://n/"},
        {"kind": "web", "target": "https://n/", "every_minutes": 1},
    ],
)
def test_rejects_bad_sources(client: TestClient, body: dict[str, object]) -> None:
    assert client.post("/api/sources", json=body).status_code == 422


def test_unknown_source_is_404(client: TestClient) -> None:
    assert client.patch("/api/sources/9", json={"enabled": True}).status_code == 404
    assert client.delete("/api/sources/9").status_code == 404


@pytest.mark.parametrize(
    ("enabled", "checked_at", "due"),
    [
        (True, None, True),
        (True, NOW - timedelta(minutes=60), True),
        (True, NOW - timedelta(minutes=59), False),
        (False, None, False),
    ],
)
def test_is_due(enabled: bool, checked_at: datetime | None, due: bool) -> None:
    row = DataSource(
        kind="web", target="https://n/", every_minutes=60, enabled=enabled, checked_at=checked_at
    )
    assert is_due(row, NOW) is due


def test_route_can_be_set_and_cleared(client: TestClient) -> None:
    added = client.post(
        "/api/sources", json={"kind": "web", "target": "https://n/", "route": "flag"}
    ).json()
    assert added["route"] == "flag"

    assert client.patch("/api/sources/1", json={"enabled": False}).json()["route"] == "flag"
    assert client.patch("/api/sources/1", json={"route": None}).json()["route"] is None


def test_unknown_route_is_rejected(client: TestClient) -> None:
    client.post("/api/sources", json={"kind": "web", "target": "https://n/"})

    assert client.patch("/api/sources/1", json={"route": "delete"}).status_code == 422
    assert client.patch("/api/sources/1", json={"route": "chat"}).status_code == 422
    assert client.get("/api/sources").json()[0]["route"] is None
