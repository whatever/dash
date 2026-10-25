import io
import uuid

import pytest
from alembic import command
from alembic.script import ScriptDirectory

from dash.db import alembic_config, async_url
from dash.hermes import Delta, HermesError, conversation_key, parse_sse_frame
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


def test_parse_sse_frame() -> None:
    text = '{"type":"response.output_text.delta","delta":"hi"}'
    assert parse_sse_frame("response.output_text.delta", text) == [Delta("text", "hi")]
    assert parse_sse_frame(None, text) == [Delta("text", "hi")]
    assert parse_sse_frame(None, "[DONE]") == []
    thinking = '{"type":"response.reasoning_summary_text.delta","delta":"hmm"}'
    assert parse_sse_frame(None, thinking) == [Delta("reasoning", "hmm")]
    call = (
        '{"type":"response.output_item.added","item":{"type":"function_call",'
        '"name":"terminal","call_id":"c1","arguments":"{\\"command\\": \\"ls -la\\"}"}}'
    )
    assert parse_sse_frame(None, call) == [
        Delta(
            "tool",
            data={"tool": "terminal", "label": "ls -la", "toolCallId": "c1", "status": "running"},
        )
    ]
    done = call.replace("added", "done")
    assert parse_sse_frame(None, done) == [
        Delta("tool", data={"tool": "terminal", "toolCallId": "c1", "status": "completed"})
    ]
    output = '{"type":"response.output_item.added","item":{"type":"function_call_output"}}'
    assert parse_sse_frame(None, output) == []
    assert parse_sse_frame("hermes.status", '{"message":"retrying"}') == [
        Delta("status", data={"message": "retrying"})
    ]
    assert parse_sse_frame("response.created", '{"type":"response.created"}') == []
    with pytest.raises(HermesError, match="boom"):
        parse_sse_frame(None, '{"type":"response.failed","response":{"error":{"message":"boom"}}}')


def test_conversation_key_is_stable() -> None:
    cid = uuid.uuid4()
    assert conversation_key(cid) == conversation_key(str(cid)) == f"dash:{cid}"


def test_parse_facts() -> None:
    assert parse_facts('Here: ["The user likes tea.", " ", 3]') == ["The user likes tea."]
    assert parse_facts("[]") == []
    assert parse_facts("no json") == []
    assert parse_facts("[not json]") == []
    assert parse_facts('{"a": [1]}') == []


def test_system_prompt() -> None:
    assert system_prompt([]) is None
    assert "- The user likes tea." in (system_prompt(["The user likes tea."]) or "")


def test_offline_upgrade_adds_routing_columns() -> None:
    config = alembic_config(URL)
    config.output_buffer = io.StringIO()

    command.upgrade(config, "head", sql=True)

    sql = config.output_buffer.getvalue()
    assert "ALTER TABLE timeline ADD COLUMN action TEXT" in sql
    assert "ALTER TABLE timeline ADD COLUMN confidence FLOAT" in sql
    assert "ALTER TABLE sources ADD COLUMN route TEXT" in sql
