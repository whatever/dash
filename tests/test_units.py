import io

from alembic import command
from alembic.script import ScriptDirectory

from dash.db import alembic_config, async_url
from dash.hermes import ENV_HEADER, Hermes, parse_sse_line
from dash.memory import parse_facts, system_prompt

URL = "postgresql://dash:p%40ss@db:5432/dash"


def test_async_url_sets_driver_and_keeps_password() -> None:
    assert async_url(URL) == "postgresql+asyncpg://dash:p%40ss@db:5432/dash"


def test_single_migration_head() -> None:
    assert len(ScriptDirectory.from_config(alembic_config(URL)).get_heads()) == 1


def test_offline_upgrade_creates_vector_tables() -> None:
    config = alembic_config(URL)
    config.output_buffer = io.StringIO()

    command.upgrade(config, "head", sql=True)

    sql = config.output_buffer.getvalue()
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert "embedding VECTOR(1024) NOT NULL" in sql
    assert "USING hnsw (embedding vector_cosine_ops)" in sql
    assert "REFERENCES conversations (id) ON DELETE CASCADE" in sql


def test_parse_sse_line() -> None:
    chunk = 'data: {"choices":[{"delta":{"content":"hi"}}]}'
    assert parse_sse_line(chunk) == "hi"
    assert parse_sse_line("data: [DONE]") is None
    assert parse_sse_line(": keep-alive") is None
    assert parse_sse_line('data: {"choices":[{"delta":{"role":"assistant"}}]}') is None
    assert parse_sse_line('data: {"choices":[]}') is None


def test_parse_facts() -> None:
    assert parse_facts('Here: ["The user likes tea.", " ", 3]') == ["The user likes tea."]
    assert parse_facts("[]") == []
    assert parse_facts("no json") == []
    assert parse_facts("[not json]") == []
    assert parse_facts('{"a": [1]}') == []


def test_system_prompt() -> None:
    assert system_prompt([]) is None
    assert "- The user likes tea." in (system_prompt(["The user likes tea."]) or "")


async def test_hermes_sends_env_header_only_when_given() -> None:
    import json

    import httpx

    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get(ENV_HEADER))
        return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"hi"}}]}\n\n')

    hermes = Hermes("http://hermes/v1", "key", "m", httpx.MockTransport(handler))

    assert [d async for d in hermes.stream([], {"GITHUB_TOKEN": "ghs_x"})] == ["hi"]
    assert [d async for d in hermes.stream([])] == ["hi"]
    assert seen[0] is not None
    assert json.loads(seen[0]) == {"GITHUB_TOKEN": "ghs_x"}
    assert seen[1] is None
