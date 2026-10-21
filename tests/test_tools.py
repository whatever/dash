import asyncio
import stat
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

import fakeredis
import httpx
import pytest
from pydantic_ai.models.function import DeltaToolCall
from pydantic_ai.toolsets import FunctionToolset

from dash.agent import Engine
from dash.agent import sandbox as sandbox_module
from dash.agent.deps import TurnDeps
from dash.agent.mcp import McpServer, ServerTools, parse
from dash.agent.policy import ToolPolicy
from dash.agent.sandbox import Sandbox, private_key_copy
from dash.agent.tools import MemoryHit, memory_tools, sandbox_tools, web_tools
from dash.agent.web import Fetcher, RefusedError, Resolve, is_public
from dash.db import Store
from dash.inbox.db import InboxStore
from dash.queue import Job, Queue
from dash.worker import Worker
from tests.fakes import FakeEmbedder, FakeExtractor, FakeInboxStore, FakeStore, ScriptedModel

SANDBOX = Sandbox("dash-sandbox", 2222, "agent", Path("/keys/id"))

Tool = Callable[[str], Awaitable[Any]]


def tool(toolset: FunctionToolset[TurnDeps], name: str) -> Tool:
    return cast("Tool", toolset.tools[name].function)


class FakeProcess:
    """A finished (or hanging) ssh process."""

    def __init__(self, out: bytes, code: int, *, hang: bool = False) -> None:
        self.out = out
        self.returncode = code
        self.hang = hang
        self.killed = False

    async def communicate(self) -> tuple[bytes, None]:
        """Return the output, or hang."""
        if self.hang:
            await asyncio.sleep(10)
        return self.out, None

    def kill(self) -> None:
        """Record that the process was killed."""
        self.killed = True

    async def wait(self) -> int:
        """Return the exit code."""
        return self.returncode


def spawn(monkeypatch: pytest.MonkeyPatch, process: FakeProcess) -> list[tuple[str, ...]]:
    calls: list[tuple[str, ...]] = []

    async def fake_exec(*argv: str, **_: Any) -> FakeProcess:
        calls.append(argv)
        return process

    monkeypatch.setattr(sandbox_module.asyncio, "create_subprocess_exec", fake_exec)
    return calls


def test_ssh_command_line() -> None:
    argv = SANDBOX.argv("git status; echo 'done'")

    assert argv[0] == "ssh"
    assert argv[1:5] == ["-i", "/keys/id", "-p", "2222"]
    assert "BatchMode=yes" in argv
    assert "UserKnownHostsFile=/keys/known_hosts" in argv
    assert argv[-2] == "agent@dash-sandbox"
    assert argv[-1] == (
        sandbox_module.EXPORT_GITHUB_TOKEN
        + "cd /config/workspace && timeout -s KILL 90 sh -c 'git status; echo '\"'\"'done'\"'\"''"
    )


def test_the_github_token_is_exported_from_its_file() -> None:
    remote = SANDBOX.argv("gh auth status")[-1]

    assert remote.startswith(
        '[ -r /run/secrets/github/token ] && export GITHUB_TOKEN="$(cat /run/secrets/github/token)"'
        ' GH_TOKEN="$(cat /run/secrets/github/token)"; cd /config/workspace'
    )


async def test_a_command_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = spawn(monkeypatch, FakeProcess(b"git version 2.47.1\n", 0))

    result = await SANDBOX.run("git --version")

    assert (result.exit_code, result.output) == (0, "git version 2.47.1\n")
    assert not result.output_cut
    assert not result.timed_out
    assert calls[0][-1].endswith("sh -c 'git --version'")


async def test_a_failing_command_returns_its_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    spawn(monkeypatch, FakeProcess(b"no such file\n", 2))

    result = await SANDBOX.run("cat nope")

    assert (result.exit_code, result.output) == (2, "no such file\n")


async def test_long_output_is_cut(monkeypatch: pytest.MonkeyPatch) -> None:
    spawn(monkeypatch, FakeProcess(b"x" * 50_000, 0))

    result = await SANDBOX.run("yes x")

    assert len(result.output) == 20_000
    assert result.output_cut


async def test_a_remote_timeout_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    spawn(monkeypatch, FakeProcess(b"", 137))

    assert (await SANDBOX.run("sleep 999")).timed_out


async def test_a_hung_connection_is_killed(monkeypatch: pytest.MonkeyPatch) -> None:
    process = FakeProcess(b"", 0, hang=True)
    spawn(monkeypatch, process)
    monkeypatch.setattr(sandbox_module, "TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(sandbox_module, "CONNECT_TIMEOUT_SECONDS", 0.05)

    result = await SANDBOX.run("sleep 999")

    assert result.timed_out
    assert result.exit_code is None
    assert process.killed


def test_the_key_is_copied_private(tmp_path: Path) -> None:
    key = tmp_path / "id_ed25519"
    key.write_text("secret")
    key.chmod(0o644)

    copy = private_key_copy(key)

    assert copy.read_text() == "secret"
    assert stat.S_IMODE(copy.stat().st_mode) == 0o600
    assert stat.S_IMODE(copy.parent.stat().st_mode) == 0o700


Handler = Callable[[httpx.Request], httpx.Response]


def addresses(table: dict[str, list[str]]) -> Resolve:
    async def fake_resolve(host: str, port: int) -> list[str]:
        return table[host]

    return fake_resolve


def fetcher(handler: Handler, table: dict[str, list[str]]) -> tuple[Fetcher, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(record))
    return Fetcher(client, addresses(table)), seen


async def test_a_public_page_comes_back_as_text() -> None:
    page = "<html><script>x()</script><h1>Hi</h1><p>there</p></html>"
    fetch, _ = fetcher(
        lambda _: httpx.Response(200, text=page, headers={"content-type": "text/html"}),
        {"example.com": ["93.184.216.34"]},
    )

    assert await fetch.fetch("https://example.com/") == "200 https://example.com/\n\nHi there"


@pytest.mark.parametrize("address", ["127.0.0.1", "10.1.2.3", "169.254.169.254", "::ffff:10.0.0.1"])
async def test_internal_addresses_are_refused_before_any_request(address: str) -> None:
    fetch, seen = fetcher(lambda _: httpx.Response(200), {"inside": [address]})

    with pytest.raises(RefusedError):
        await fetch.fetch("http://inside/")

    assert seen == []


async def test_a_redirect_to_an_internal_address_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://metadata/latest"})

    fetch, seen = fetcher(handler, {"example.com": ["93.184.216.34"], "metadata": ["10.0.0.1"]})

    with pytest.raises(RefusedError):
        await fetch.fetch("http://example.com/")

    assert [str(r.url) for r in seen] == ["http://example.com/"]


async def test_too_many_redirects_are_refused() -> None:
    fetch, _ = fetcher(
        lambda r: httpx.Response(302, headers={"location": str(r.url) + "x"}),
        {"example.com": ["93.184.216.34"]},
    )

    with pytest.raises(RefusedError, match="redirects"):
        await fetch.fetch("http://example.com/")


async def test_other_schemes_are_refused() -> None:
    fetch, _ = fetcher(lambda _: httpx.Response(200), {})

    with pytest.raises(RefusedError, match="http and https"):
        await fetch.fetch("file:///etc/passwd")


async def test_the_fetch_tool_reports_a_refusal() -> None:
    fetch, _ = fetcher(lambda _: httpx.Response(200), {"inside": ["127.0.0.1"]})
    fetch_url = tool(web_tools(fetch), "fetch_url")

    assert str(await fetch_url("http://inside/")).startswith("Refused:")


def test_public_addresses() -> None:
    assert is_public("93.184.216.34")
    assert not is_public("100.64.0.1")
    assert not is_public("fd00::1")
    assert not is_public("224.0.0.1")


async def test_memory_tools_search_and_remember() -> None:
    store, embedder = FakeStore(), FakeEmbedder()
    tools = memory_tools(cast("Store", store), embedder)
    remember, search = tool(tools, "remember"), tool(tools, "search_memories")

    assert await remember("The user prefers Celsius.") == "Remembered."
    assert str(await remember("The user prefers Celsius.")).startswith("Already known")
    assert [(m.content, m.source) for m in store.mems] == [("The user prefers Celsius.", "agent")]
    hits = await search("The user prefers Celsius.")
    assert hits == [MemoryHit(content="The user prefers Celsius.", distance=0.0)]


def test_policy_verdicts() -> None:
    policy = ToolPolicy.parse('{"run_command": "never", "serena_*": "ask", "serena_find": "auto"}')

    assert policy.verdict("run_command") == "never"
    assert policy.verdict("serena_list_dir") == "ask"
    assert policy.verdict("serena_find") == "auto"
    assert policy.verdict("fetch_url") == "auto"
    assert ToolPolicy.parse("").verdict("anything") == "auto"


def server_tools() -> FunctionToolset[TurnDeps]:
    tools = FunctionToolset[TurnDeps]()

    @tools.tool_plain
    def find(pattern: str) -> str:
        """Find a symbol."""
        return pattern

    @tools.tool_plain
    def execute_shell_command(command: str) -> str:
        """Run a command."""
        return command

    return tools


async def offered(model: ScriptedModel, engine: Engine) -> list[str]:
    store = FakeStore()
    conv = await store.create_conversation()
    await store.add_message(conv.id, "user", "hi")
    worker = Worker(
        store=cast("Store", store),
        inbox=cast("InboxStore", FakeInboxStore()),
        queue=Queue(fakeredis.FakeAsyncRedis(decode_responses=True)),
        agent=engine,
        embedder=FakeEmbedder(),
        extractor=FakeExtractor([]),
        top_k=8,
    )
    await worker.handle(Job("1-0", "job", str(conv.id)))
    return sorted(t.name for t in model.infos[0].function_tools)


async def test_never_hides_a_tool_and_a_whole_server() -> None:
    model = ScriptedModel(["ok"])
    policy = ToolPolicy.parse('{"execute_shell_command": "never", "serena_*": "never"}')
    servers = [ServerTools.build("serena", server_tools(), [])]
    engine = model.engine([server_tools()], policy=policy, servers=servers)

    assert await offered(model, engine) == ["find"]


async def test_servers_are_prefixed_and_exclusions_left_out() -> None:
    model = ScriptedModel(["ok"])
    servers = [ServerTools.build("serena", server_tools(), ["execute_shell_command"])]
    assert await offered(model, model.engine(servers=servers)) == ["serena_find"]


async def test_an_unreachable_server_is_left_out_with_a_status() -> None:
    model = ScriptedModel(["ok"])
    down = ServerTools.connect(McpServer(name="down", url="http://127.0.0.1:9/mcp"))
    store = FakeStore()
    conv = await store.create_conversation()
    await store.add_message(conv.id, "user", "hi")
    queue = Queue(fakeredis.FakeAsyncRedis(decode_responses=True))
    worker = Worker(
        store=cast("Store", store),
        inbox=cast("InboxStore", FakeInboxStore()),
        queue=queue,
        agent=model.engine(servers=[down]),
        embedder=FakeEmbedder(),
        extractor=FakeExtractor([]),
        top_k=8,
    )

    await worker.handle(Job("1-0", "job", str(conv.id)))

    events = [e async for e in queue.events("job")]
    assert events[0]["kind"] == "status"
    assert "down" in events[0]["message"]
    assert events[-1]["kind"] == "done"


async def test_a_tool_call_runs_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    spawn(monkeypatch, FakeProcess(b"git version 2.47.1\n", 0))
    model = ScriptedModel(
        [{0: DeltaToolCall(name="run_command", json_args='{"command": "git --version"}')}],
        ["It is 2.47.1."],
    )
    engine = model.engine([sandbox_tools(SANDBOX)])

    assert await offered(model, engine) == ["run_command"]
    returned = [str(p) for m in model.requests[-1] for p in m.parts if "git version" in str(p)]
    assert returned


def test_mcp_servers_parse() -> None:
    assert parse("") == []
    assert parse('[{"name": "serena", "url": "http://s:9121/mcp", "exclude": ["x"]}]') == [
        McpServer(name="serena", url="http://s:9121/mcp", exclude=["x"])
    ]


async def test_a_printed_github_token_is_masked(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "ghs_" + "a1B2c3D4e5F6g7H8i9J0k1L2"
    pat = "github_pat_" + "x" * 30
    spawn(
        monkeypatch,
        FakeProcess(f"GITHUB_TOKEN={token}\nremote https://x:{pat}@github.com\n".encode(), 0),
    )

    result = await SANDBOX.run("env")

    assert token not in result.output
    assert pat not in result.output
    assert result.output == "GITHUB_TOKEN=***\nremote https://x:***@github.com\n"
