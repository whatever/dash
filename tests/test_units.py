import io

import pytest
from alembic import command
from alembic.script import ScriptDirectory

from dash.agent import tool_label
from dash.config import Settings
from dash.db import alembic_config, async_url
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
    assert "CREATE TABLE turn_history" in sql


def test_tool_label() -> None:
    assert tool_label('{"command": "ls   -la"}') == "ls -la"
    assert tool_label({"command": "git status"}) == "git status"
    assert tool_label({"a": 1, "b": 2}) == '{"a": 1, "b": 2}'
    assert tool_label("not json") == "not json"
    assert tool_label(None) == "{}"
    assert tool_label({"text": "x" * 200}) == "x" * 119 + "\u2026"


def test_settings_read_the_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setenv("AGENT_BASE_URL", "http://litellm:4000/v1/")
    monkeypatch.setenv("AGENT_THINKING", "low")

    settings = Settings.from_env()

    assert settings.agent_model == "bedrock:global.anthropic.claude-opus-5-5"
    assert settings.agent_base_url == "http://litellm:4000/v1"
    assert settings.agent_thinking == "low"
    assert (settings.agent_request_limit, settings.agent_tool_call_limit) == (60, 100)


def test_settings_reject_an_unknown_thinking_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setenv("AGENT_THINKING", "lots")

    with pytest.raises(RuntimeError, match="AGENT_THINKING"):
        Settings.from_env()


def test_parse_facts() -> None:
    assert parse_facts('Here: ["The user likes tea.", " ", 3]') == ["The user likes tea."]
    assert parse_facts("[]") == []
    assert parse_facts("no json") == []
    assert parse_facts("[not json]") == []
    assert parse_facts('{"a": [1]}') == []


def test_system_prompt() -> None:
    assert system_prompt([]) is None
    assert "- The user likes tea." in (system_prompt(["The user likes tea."]) or "")
