import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import fakeredis
from fastapi.testclient import TestClient
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    RetryPromptPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import DeltaToolCall
from pydantic_ai.toolsets import FunctionToolset

from dash.agent.deps import TurnDeps
from dash.agent.policy import ToolPolicy
from dash.agent.tools import inbox_tools
from dash.db import Store
from dash.inbox.api import create_router
from dash.inbox.db import InboxStore
from dash.nango import Nango
from dash.queue import JOBS, RESUME, Job, Queue
from dash.web import create_app
from dash.worker import Worker
from tests.fakes import Chunk, FakeEmbedder, FakeExtractor, FakeInboxStore, FakeStore, ScriptedModel

ASK_RUN = ToolPolicy.parse('{"run_command": "ask"}')


def call(command: str, call_id: str = "c1", index: int = 0) -> dict[int, Any]:
    return {
        index: DeltaToolCall(
            name="run_command", json_args=f'{{"command": "{command}"}}', tool_call_id=call_id
        )
    }


def command_tools(ran: list[str]) -> FunctionToolset[TurnDeps]:
    tools = FunctionToolset[TurnDeps]()

    @tools.tool_plain
    def run_command(command: str) -> str:
        """Run a command."""
        ran.append(command)
        return f"ran {command}"

    return tools


@dataclass
class Rig:
    worker: Worker
    store: FakeStore
    inbox: FakeInboxStore
    queue: Queue
    model: ScriptedModel
    conv_id: uuid.UUID
    ran: list[str]
    client: TestClient

    async def events(self, job_id: str) -> list[dict[str, Any]]:
        return [e async for e in self.queue.events(job_id)]

    async def chat(self, job_id: str, text: str | None = None) -> list[dict[str, Any]]:
        if text is not None:
            await self.store.add_message(self.conv_id, "user", text)
        await self.worker.handle(Job("1-0", job_id, str(self.conv_id)))
        return await self.events(job_id)

    async def resume(self, job_id: str, item_ids: list[int]) -> list[dict[str, Any]]:
        job = Job("2-0", job_id, str(self.conv_id), kind=RESUME, data={"item_ids": item_ids})
        await self.worker.handle(job)
        return await self.events(job_id)


async def rig(*responses: list[Chunk], policy: ToolPolicy = ASK_RUN) -> Rig:
    store, inbox = FakeStore(), FakeInboxStore()
    queue = Queue(fakeredis.FakeAsyncRedis(decode_responses=True))
    model = ScriptedModel(*responses)
    ran: list[str] = []
    tools = [command_tools(ran), inbox_tools(cast("InboxStore", inbox))]
    worker = Worker(
        store=cast("Store", store),
        inbox=cast("InboxStore", inbox),
        queue=queue,
        agent=model.engine(tools, policy=policy),
        embedder=FakeEmbedder(),
        extractor=FakeExtractor([]),
        top_k=8,
    )
    app = create_app(
        store=cast("Store", store),
        queue=queue,
        embedder=FakeEmbedder(),
        nango=Nango("http://nango.invalid", ""),
        routers=[create_router(store=cast("InboxStore", inbox), queue=queue)],
    )
    conv = await store.create_conversation()
    await store.add_message(conv.id, "user", "push my branch")
    return Rig(worker, store, inbox, queue, model, conv.id, ran, TestClient(app))


def tool_returns(messages: list[ModelMessage]) -> list[str]:
    return [
        str(part.content)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]


async def test_an_ask_tool_waits_for_approval() -> None:
    r = await rig(["Pushing now. ", call("git push")])

    got = await r.chat("t1")

    assert r.ran == []
    item = r.inbox.rows[0]
    assert (item.kind, item.status, item.data["tool"], item.data["args"]) == (
        "approval",
        "open",
        "run_command",
        {"command": "git push"},
    )
    assert got[-2] == {
        "kind": "approval",
        "item_id": item.id,
        "conversation_id": str(r.conv_id),
        "tool": "run_command",
        "label": "git push",
        "toolCallId": "c1",
    }
    assert got[-1]["kind"] == "done"
    assert got[-1]["awaiting"] == [item.id]
    assert (await r.store.messages(r.conv_id))[-1].content == "Pushing now. "


async def test_allowing_resumes_the_turn() -> None:
    r = await rig([call("git push")], ["Pushed."])
    await r.chat("t1")
    item_id = r.inbox.rows[0].id

    response = r.client.post(f"/api/inbox/{item_id}/resolve", json={"decision": "allow"})

    assert response.status_code == 202
    job_id = response.json()["job_id"]
    got = await r.resume(job_id, [item_id])
    assert r.ran == ["git push"]
    assert "".join(e.get("text", "") for e in got if e["kind"] == "delta") == "Pushed."
    assert [m.content for m in await r.store.messages(r.conv_id)][-1] == "Pushed."
    assert tool_returns(r.model.requests[-1]) == ["ran git push"]


async def test_denying_tells_the_model() -> None:
    r = await rig([call("git push")], ["Okay, I won't."])
    await r.chat("t1")
    item_id = r.inbox.rows[0].id

    job_id = r.client.post(f"/api/inbox/{item_id}/resolve", json={"decision": "deny"}).json()[
        "job_id"
    ]
    got = await r.resume(job_id, [item_id])

    assert r.ran == []
    assert tool_returns(r.model.requests[-1]) == ["The person denied this call."]
    assert {"kind": "tool", "tool": "run_command", "toolCallId": "c1", "status": "denied"} in got


async def test_allow_always_saves_a_rule_for_the_tool() -> None:
    note = {
        0: DeltaToolCall(
            name="leave_message", json_args='{"title": "Hi", "body": "Yo"}', tool_call_id="c3"
        )
    }
    r = await rig(
        [call("git status")],
        ["Clean."],
        [call("git push", "c2")],
        ["Pushed."],
        [note],
        policy=ToolPolicy.parse('{"run_command": "ask", "leave_message": "ask"}'),
    )
    await r.chat("t1")
    first = r.inbox.rows[0].id
    job_id = r.client.post(f"/api/inbox/{first}/resolve", json={"decision": "allow_always"}).json()[
        "job_id"
    ]
    await r.resume(job_id, [first])

    await r.chat("t2", "now push")
    assert r.ran == ["git status", "git push"]
    assert len(r.inbox.rows) == 1
    assert r.client.get("/api/inbox/rules").json() == [
        {"id": r.inbox.tool_rules[0].id, "tool": "run_command", "args": {}}
    ]

    await r.chat("t3", "leave a note")
    assert [i.data["tool"] for i in r.inbox.rows] == ["run_command", "leave_message"]


async def test_a_rule_applies_in_another_conversation() -> None:
    r = await rig([call("git push")], ["Pushed."])
    await r.inbox.add_rule("run_command")
    other = await r.store.create_conversation()
    await r.store.add_message(other.id, "user", "push it")

    await r.worker.handle(Job("1-0", "t9", str(other.id)))

    assert r.ran == ["git push"]
    assert r.inbox.rows == []


async def test_two_approvals_resume_only_after_both() -> None:
    r = await rig([{**call("one", "c1"), **call("two", "c2", 1)}], ["Both ran."])
    await r.chat("t1")
    first, second = (i.id for i in r.inbox.rows)

    assert r.client.post(f"/api/inbox/{first}/resolve", json={"decision": "allow"}).json() == {}
    job_id = r.client.post(f"/api/inbox/{second}/resolve", json={"decision": "deny"}).json()[
        "job_id"
    ]
    await r.resume(job_id, [first, second])

    assert r.ran == ["one"]
    assert sorted(tool_returns(r.model.requests[-1])) == ["The person denied this call.", "ran one"]


async def test_answering_twice_changes_nothing() -> None:
    r = await rig([call("git push")], ["Pushed."])
    await r.chat("t1")
    item_id = r.inbox.rows[0].id
    first = r.client.post(f"/api/inbox/{item_id}/resolve", json={"decision": "deny"})

    again = r.client.post(f"/api/inbox/{item_id}/resolve", json={"decision": "allow"})

    assert first.status_code == 202
    assert again.status_code == 200
    assert again.json() == {
        "resolution": {"decision": "deny", "reason": ""},
        "job_id": first.json()["job_id"],
    }
    assert r.inbox.rows[0].resolution == {"decision": "deny", "reason": ""}
    assert await r.queue.redis.xlen(JOBS) == 1
    assert r.client.post("/api/inbox/999/resolve", json={"decision": "allow"}).status_code == 404


async def test_a_single_item_can_be_read() -> None:
    r = await rig([call("git push")])
    await r.chat("t1")
    item_id = r.inbox.rows[0].id

    body = r.client.get(f"/api/inbox/{item_id}").json()

    assert (body["id"], body["status"], body["conversation_id"]) == (
        item_id,
        "open",
        str(r.conv_id),
    )
    assert r.client.get("/api/inbox/999").status_code == 404


async def test_a_new_message_supersedes_open_approvals() -> None:
    r = await rig([call("git push")], ["Sure, here's the status."])
    await r.chat("t1")

    await r.chat("t2", "never mind, just show the status")

    item = r.inbox.rows[0]
    assert (item.status, item.resolution) == (
        "resolved",
        {"decision": "deny", "reason": "superseded"},
    )
    sent = r.model.requests[-1]
    assert tool_returns(sent)[0].startswith("The person sent a new message")
    prompts = [
        p.content
        for m in sent
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, UserPromptPart)
    ]
    assert prompts[-1] == "never mind, just show the status"
    assert r.ran == []


async def test_old_approvals_expire_and_count_as_denied() -> None:
    r = await rig([call("git push")], ["Okay."])
    await r.chat("t1")
    item = r.inbox.rows[0]
    item.created_at = datetime.now(UTC) - timedelta(hours=25)

    await r.worker.sweep()

    assert item.status == "expired"
    assert (
        r.client.post(f"/api/inbox/{item.id}/resolve", json={"decision": "allow"}).status_code
        == 409
    )
    await r.chat("t2", "hello?")
    assert tool_returns(r.model.requests[-1])[0].startswith("No one answered within 24 hours")


async def test_the_agent_can_leave_a_message() -> None:
    note = {
        0: DeltaToolCall(
            name="leave_message",
            json_args='{"title": "Build is green", "body": "CI passed.", "sources": ["https://ci/1"]}',
        )
    }
    r = await rig([note], ["Noted."], policy=ToolPolicy())

    await r.chat("t1")

    item = r.inbox.rows[0]
    assert (item.kind, item.title, item.body, item.data) == (
        "message",
        "Build is green",
        "CI passed.",
        {"sources": ["https://ci/1"]},
    )
    assert item.conversation_id == r.conv_id
    assert r.client.get("/api/inbox/count").json() == {"open": 1}


async def test_inbox_lists_and_dismisses() -> None:
    r = await rig([call("git push")], policy=ASK_RUN)
    await r.chat("t1")
    message = await r.inbox.add(
        kind="message", title="Note", data={}, conversation_id=r.conv_id, job_id="t1"
    )
    approval = r.inbox.rows[0]

    assert [i["id"] for i in r.client.get("/api/inbox").json()] == [message.id, approval.id]
    assert r.client.post(f"/api/inbox/{approval.id}/dismiss").status_code == 409
    assert r.client.post(f"/api/inbox/{message.id}/dismiss").status_code == 204
    assert r.client.post(f"/api/inbox/{message.id}/dismiss").status_code == 409
    assert r.client.post("/api/inbox/999/dismiss").status_code == 404
    assert [i["id"] for i in r.client.get("/api/inbox").json()] == [approval.id]
    assert len(r.client.get("/api/inbox?status=all").json()) == 2
    assert r.client.get("/api/inbox/count").json() == {"open": 1}


async def test_rules_can_be_deleted() -> None:
    r = await rig()
    await r.inbox.add_rule("run_command")
    rule_id = r.inbox.tool_rules[0].id

    assert r.client.delete(f"/api/inbox/rules/{rule_id}").status_code == 204
    assert r.client.delete(f"/api/inbox/rules/{rule_id}").status_code == 404
    assert r.client.get("/api/inbox/rules").json() == []


async def test_a_resume_without_waiting_calls_errors() -> None:
    r = await rig(["hi"])
    await r.chat("t1")

    got = await r.resume("r1", [])

    assert got[-1] == {"kind": "error", "message": "Nothing to resume."}


async def test_a_resume_is_queued_once_per_turn() -> None:
    queue = Queue(fakeredis.FakeAsyncRedis(decode_responses=True))
    await queue.ensure_group()

    first = await queue.enqueue_resume("t1", "c", [1])
    second = await queue.enqueue_resume("t1", "c", [1])

    assert first is not None
    assert second is None
    job = await queue.claim("w", block_ms=10)
    assert job is not None
    assert (job.kind, job.conversation_id, job.data) == ("resume", "c", {"item_ids": [1]})


async def test_an_oversized_message_is_sent_back_to_the_model() -> None:
    long_title = "x" * 121
    note = {
        0: DeltaToolCall(
            name="leave_message", json_args=f'{{"title": "{long_title}", "body": "b"}}'
        )
    }
    r = await rig([note], ["Sorry, I'll keep it short."], policy=ToolPolicy())

    await r.chat("t1")

    assert r.inbox.rows == []
    retried = [
        p
        for m in r.model.requests[-1]
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, RetryPromptPart)
    ]
    assert retried


async def test_never_hides_leave_message() -> None:
    r = await rig(["ok"], policy=ToolPolicy.parse('{"leave_message": "never"}'))

    await r.chat("t1")

    assert "leave_message" not in {t.name for t in r.model.infos[0].function_tools}
