import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import fakeredis
import pytest
from pydantic_ai.models.function import DeltaToolCall
from pydantic_ai.toolsets import FunctionToolset

from dash import wiki as wiki_module
from dash.agent.deps import TurnDeps
from dash.agent.sandbox import CommandResult
from dash.agent.tools import wiki_tools
from dash.agent.workspace import DEFAULT_PROFILE, Profile
from dash.db import Store
from dash.inbox import MESSAGE
from dash.inbox.db import InboxStore
from dash.queue import DREAM, Job, Queue
from dash.wiki import (
    DREAM_PROFILE,
    WIKI_HINT,
    Wiki,
    lint,
    parse_pages,
    render_transcripts,
    with_wiki,
)
from dash.worker import Worker
from tests.fakes import FakeEmbedder, FakeExtractor, FakeInboxStore, FakeStore, ScriptedModel

PAGE = "---\nname: oakland\ndescription: Where the user lives.\n---\nLives in Oakland.\n"
INDEX = "# Index\n\n- [[oakland]] — where the user lives\n"


class LocalRunner:
    """Runs sandbox commands in a local shell."""

    async def run(self, command: str, *, session: str, profile: Profile) -> CommandResult:
        """Return the result of the given command run with `sh -c`."""
        process = await asyncio.create_subprocess_exec(
            "sh",
            "-c",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await process.communicate()
        return CommandResult(exit_code=process.returncode, output=out.decode())


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "wiki"
    monkeypatch.setattr(wiki_module, "WIKI_ROOT", str(path))
    return path


def test_a_clean_wiki_has_no_problems() -> None:
    assert lint({"oakland.md": PAGE, "_index.md": INDEX, "WIKI.md": "# How"}) == []


def test_lint_finds_what_is_wrong() -> None:
    pages = {
        "bare.md": "no frontmatter",
        "wrong.md": "---\nname: other\ndescription: x\n---\nSee [[nowhere]].\n",
        "empty.md": "---\nname: empty\ndescription:\n---\n",
        "_index.md": "- [[wrong]]\n- [[ghost]]\n",
    }

    assert lint(pages) == [
        "bare: no frontmatter",
        "empty: no description",
        "wrong: name is not wrong",
        "wrong: links to missing page nowhere",
        "_index: does not list bare",
        "_index: does not list empty",
        "_index: lists missing page ghost",
    ]


def test_lint_needs_an_index_and_a_size_limit() -> None:
    big = PAGE + "x" * 100_000

    assert lint({"oakland.md": PAGE}) == ["_index: missing"]
    assert "oakland: larger than 100 KB" in lint({"oakland.md": big, "_index.md": INDEX})


def test_pages_parse_from_the_listing() -> None:
    output = f"\n{wiki_module.FILE_MARK} a.md\none\ntwo\n\n{wiki_module.FILE_MARK} b.md\nthree\n"

    assert parse_pages(output) == {"a.md": "one\ntwo\n", "b.md": "three\n"}
    assert parse_pages("") == {}


def test_transcripts_are_cut_to_the_limit_keeping_the_first() -> None:
    conversations = [
        ("New", "1", [("user", "hello")]),
        ("Old", "2", [("user", "y" * 500)]),
    ]

    text = render_transcripts(conversations, limit=100)

    assert "## New (1)\nuser: hello" in text
    assert "Old" not in text
    assert "x" * 4_001 not in render_transcripts([("T", "1", [("user", "x" * 9_000)])])


def test_the_wiki_is_mounted_read_only_for_chat_and_writable_for_dreams() -> None:
    profiles = with_wiki({DEFAULT_PROFILE: Profile(github=False)})

    assert [(m.path, m.mode) for m in profiles[DEFAULT_PROFILE].mounts] == [("wiki", "ro")]
    assert not profiles[DEFAULT_PROFILE].github
    assert [(m.path, m.mode) for m in profiles[DREAM_PROFILE].mounts] == [("wiki", "rw")]
    assert not profiles[DREAM_PROFILE].github


async def test_the_wiki_is_seeded_once_and_changes_are_committed(root: Path) -> None:
    wiki = Wiki(LocalRunner())

    await wiki.ensure()
    await wiki.ensure()
    assert await wiki.commit("nothing") == ""
    (root / "oakland.md").write_text(PAGE)
    (root / "_index.md").write_text(INDEX)
    stat = await wiki.commit("add oakland")

    assert "oakland.md" in stat
    assert set(await wiki.pages()) == {"WIKI.md", "_index.md", "oakland.md"}
    assert lint(await wiki.pages()) == []
    assert "CONFLICT" in (root / "WIKI.md").read_text()


async def test_pages_can_be_read_and_searched(root: Path) -> None:
    wiki = Wiki(LocalRunner())
    await wiki.ensure()
    (root / "oakland.md").write_text(PAGE)

    assert await wiki.read("oakland") == PAGE
    assert (await wiki.read("_index")).startswith("# Index")
    assert await wiki.read("nope") == "No page named 'nope'."
    assert "names use letters" in await wiki.read("../etc/passwd")
    assert "oakland.md:5:Lives in Oakland." in await wiki.search("LIVES IN")
    assert await wiki.search("zebra") == "No matches."
    assert await wiki.search("a'; rm -rf /; echo '") == "No matches."


async def test_the_agent_can_read_the_wiki_with_tools(root: Path) -> None:
    wiki = Wiki(LocalRunner())
    await wiki.ensure()
    tools = wiki_tools(wiki)

    assert sorted(tools.tools) == ["read_wiki", "search_wiki"]
    assert (await tool(tools, "read_wiki")()).startswith("# Index")
    assert await tool(tools, "search_wiki")("zebra") == "No matches."


async def test_a_failing_command_raises(root: Path) -> None:
    class Failing:
        async def run(self, command: str, *, session: str, profile: Profile) -> CommandResult:
            return CommandResult(exit_code=1, output="boom")

    with pytest.raises(RuntimeError, match="boom"):
        await Wiki(Failing()).ensure()


async def test_only_one_dream_is_queued_at_a_time() -> None:
    queue = Queue(fakeredis.FakeAsyncRedis(decode_responses=True))

    first = await queue.enqueue_dream()
    assert first
    assert await queue.enqueue_dream() is None
    await queue.finish_dream(datetime(2026, 11, 1, tzinfo=UTC))

    assert await queue.dream_since() == datetime(2026, 11, 1, tzinfo=UTC)
    assert await queue.enqueue_dream()


def tool(toolset: FunctionToolset[TurnDeps], name: str) -> Callable[..., Awaitable[str]]:
    return cast("Callable[..., Awaitable[str]]", toolset.tools[name].function)


def dream_worker(
    model: ScriptedModel, tools: FunctionToolset[TurnDeps], wiki: Wiki | None
) -> tuple[Worker, FakeStore, FakeInboxStore, Queue]:
    store, inbox = FakeStore(), FakeInboxStore()
    queue = Queue(fakeredis.FakeAsyncRedis(decode_responses=True))
    worker = Worker(
        store=cast("Store", store),
        inbox=cast("InboxStore", inbox),
        queue=queue,
        agent=ScriptedModel().engine([]),
        dream_agent=model.engine([tools]),
        embedder=FakeEmbedder(),
        extractor=FakeExtractor([]),
        top_k=8,
        wiki=wiki,
    )
    return worker, store, inbox, queue


def shell_tools(runner: LocalRunner) -> FunctionToolset[TurnDeps]:
    tools = FunctionToolset[TurnDeps]()

    @tools.tool_plain
    async def run_command(command: str) -> str:
        """Run a command."""
        return (await runner.run(command, session="s", profile=Profile())).output

    @tools.tool_plain
    async def fetch_url(url: str) -> str:
        """Fetch a page."""
        return url

    return tools


async def test_a_dream_with_nothing_new_does_nothing() -> None:
    model = ScriptedModel()
    worker, _, inbox, queue = dream_worker(model, shell_tools(LocalRunner()), Wiki(LocalRunner()))

    await worker.handle(Job("1-0", "dream", kind=DREAM))

    assert model.requests == []
    assert inbox.rows == []
    assert await queue.dream_since() is not None


async def test_a_dream_folds_conversations_into_the_wiki(root: Path) -> None:
    page = "---\\nname: oakland\\ndescription: Where the user lives.\\n---\\nLives in Oakland.\\n"
    write = json.dumps({"command": f"printf '{page}' > {root}/oakland.md"})
    model = ScriptedModel(
        [{0: DeltaToolCall(name="run_command", json_args=write)}], ["Added oakland."]
    )
    runner = LocalRunner()
    worker, store, inbox, queue = dream_worker(model, shell_tools(runner), Wiki(runner))
    chat = await store.create_conversation("Moving")
    await store.add_message(chat.id, "user", "I moved to Oakland last week")
    await queue.enqueue_dream()

    await worker.handle(Job("1-0", "dream", kind=DREAM))

    prompt = json.dumps([str(m) for m in model.requests[0]])
    assert "I moved to Oakland last week" in prompt
    assert sorted(t.name for t in model.infos[0].function_tools) == ["run_command"]
    assert any(c.title.startswith("Dream") for c in await store.conversations())
    assert [r.kind for r in inbox.rows] == [MESSAGE]
    assert "oakland.md" in inbox.rows[0].body
    assert "_index: does not list oakland" in inbox.rows[0].body
    assert await queue.dream_since() is not None
    assert await queue.enqueue_dream()

    await worker.handle(Job("2-0", "dream", kind=DREAM))

    assert len(model.requests) == 2


async def test_a_dream_without_a_wiki_reports_an_error() -> None:
    model = ScriptedModel()
    worker, _, _, queue = dream_worker(model, shell_tools(LocalRunner()), None)

    await worker.handle(Job("1-0", "job", kind=DREAM))

    assert [e["kind"] async for e in queue.events("job")] == ["error"]


async def test_chat_is_told_where_the_wiki_is() -> None:
    worker, _, _, _ = dream_worker(ScriptedModel(), shell_tools(LocalRunner()), Wiki(LocalRunner()))
    bare, _, _, _ = dream_worker(ScriptedModel(), shell_tools(LocalRunner()), None)

    assert WIKI_HINT in (worker.chat_instructions(["The user likes tea."]) or "")
    assert "The user likes tea." in (worker.chat_instructions(["The user likes tea."]) or "")
    assert bare.chat_instructions([]) is None
