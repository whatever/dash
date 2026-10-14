import json
from typing import cast

import fakeredis
import httpx
import pytest
from click.testing import CliRunner

import dash
from dash.db import Store
from dash.queue import JOBS, UPDATE, Job, Queue
from dash.sources import Item, Source, fetch, parse_feed, parse_page, parse_reddit
from dash.sources.scrape import scrape
from dash.worker import Worker
from tests.fakes import FakeChat, FakeEmbedder, FakeExtractor, FakeStore

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Big &amp; news</title><link>https://n.example/1</link><guid>g1</guid>
<description>&lt;p&gt;Something  happened.&lt;/p&gt;</description>
<pubDate>Wed, 14 Oct 2026 09:00:00 GMT</pubDate></item>
<item><title>Second</title><link>https://n.example/2</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Atom post</title><id>urn:a1</id>
<link rel="alternate" href="https://a.example/1"/><updated>2026-10-14T09:00:00Z</updated>
<summary>Short.</summary></entry></feed>"""

REDDIT = {
    "data": {
        "children": [
            {"data": {"name": "t3_pin", "stickied": True, "title": "Rules"}},
            {
                "data": {
                    "name": "t3_abc",
                    "title": "Python 3.15 is out",
                    "permalink": "/r/python/comments/abc/x/",
                    "selftext": "Yes!",
                    "created_utc": 1792000000.0,
                }
            },
        ]
    }
}


def test_source_parse() -> None:
    assert Source.parse("reddit:r/python") == Source("reddit", "python")
    assert str(Source.parse("rss:https://x/feed")) == "rss:https://x/feed"
    for bad in ("nope", "ftp:x", "rss:"):
        with pytest.raises(ValueError, match="Bad source"):
            Source.parse(bad)


def test_parse_rss_and_atom() -> None:
    items = parse_feed("rss:f", RSS)
    assert [(i.key, i.title, i.url) for i in items] == [
        ("g1", "Big & news", "https://n.example/1"),
        ("https://n.example/2", "Second", "https://n.example/2"),
    ]
    assert items[0].summary == "Something happened."
    (atom,) = parse_feed("rss:a", ATOM)
    assert (atom.key, atom.url, atom.summary) == ("urn:a1", "https://a.example/1", "Short.")


def test_parse_reddit_skips_stickied() -> None:
    (post,) = parse_reddit("reddit:python", REDDIT)
    assert post.key == "t3_abc"
    assert post.url == "https://www.reddit.com/r/python/comments/abc/x/"


def test_parse_page_key_changes_with_text() -> None:
    page = "<html><title>Status</title><script>x()</script><body>All good</body></html>"
    (a,) = parse_page("web:u", "https://s/", page)
    (b,) = parse_page("web:u", "https://s/", page.replace("good", "bad"))
    assert a.title == "Status"
    assert "x()" not in a.summary
    assert a.key != b.key


async def test_fetch_uses_the_right_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.reddit.com":
            assert request.url.path == "/r/python/new.json"
            return httpx.Response(200, json=REDDIT)
        return httpx.Response(200, content=RSS)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        assert len(await fetch(Source.parse("reddit:python"), http)) == 1
        assert len(await fetch(Source.parse("rss:https://n.example/feed"), http)) == 2


@pytest.fixture
def queue() -> Queue:
    return Queue(fakeredis.FakeAsyncRedis(decode_responses=True))


async def test_scrape_enqueues_only_new_items_and_survives_failures(queue: Queue) -> None:
    good, bad = Source.parse("rss:https://ok/"), Source.parse("rss:https://down/")

    async def fetcher(source: Source, http: httpx.AsyncClient) -> list[Item]:
        if source == bad:
            raise httpx.ConnectError("down")
        return parse_feed(str(source), RSS)

    dry = await scrape([good, bad], queue, dry_run=True, fetcher=fetcher)
    assert len(dry.enqueued) == 2
    assert await queue.redis.xlen(JOBS) == 0

    first = await scrape([good, bad], queue, fetcher=fetcher)
    assert (first.found, len(first.enqueued)) == (2, 2)
    assert first.failed == {"rss:https://down/": "down"}
    second = await scrape([good, bad], queue, fetcher=fetcher)
    assert (second.found, len(second.enqueued)) == (2, 0)

    await queue.ensure_group()
    job = await queue.claim("w", block_ms=10)
    assert job is not None
    assert job.kind == UPDATE
    assert job.data["title"] == "Big & news"


async def test_legacy_entries_are_chat_jobs(queue: Queue) -> None:
    await queue.ensure_group()
    await queue.redis.xadd(JOBS, {"job_id": "j", "conversation_id": "c"})
    job = await queue.claim("w", block_ms=10)
    assert job is not None
    assert (job.kind, job.conversation_id) == ("chat", "c")


async def test_worker_stores_update_once(queue: Queue) -> None:
    store = FakeStore()
    worker = Worker(
        store=cast("Store", store),
        queue=queue,
        chat=FakeChat([]),
        embedder=FakeEmbedder(),
        extractor=FakeExtractor([]),
        top_k=8,
    )
    (item,) = parse_reddit("reddit:python", REDDIT)
    await worker.handle(Job("1-0", "j1", kind=UPDATE, data=item.to_dict()))
    await worker.handle(Job("2-0", "j2", kind=UPDATE, data=item.to_dict()))

    assert [m.content for m in store.mems] == [item.text()]
    assert store.mems[0].source == "scrape"
    assert store.mems[0].tags == ["reddit", "reddit:python"]
    assert [e async for e in queue.events("j2")] == [{"kind": "done", "stored": False}]


def test_cli_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    monkeypatch.setattr(Queue, "from_url", classmethod(lambda cls, url: cls(redis)))

    async def fake_fetch(source: Source, http: httpx.AsyncClient) -> list[Item]:
        return parse_feed(str(source), RSS)

    monkeypatch.setattr("dash.sources.scrape.fetch", fake_fetch)
    result = CliRunner().invoke(dash.main, ["scrape", "-s", "rss:https://n/", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "new rss:https://n/ Big & news" in result.output


def test_cli_needs_sources() -> None:
    result = CliRunner().invoke(dash.main, ["scrape"], env={"SCRAPE_SOURCES": ""})
    assert result.exit_code == 2
    assert "No sources" in result.output
    bad = CliRunner().invoke(dash.main, ["scrape", "-s", "gopher:x"])
    assert bad.exit_code == 2


def test_update_payload_round_trips() -> None:
    (item,) = parse_reddit("reddit:python", REDDIT)
    assert Item.from_dict(json.loads(json.dumps(item.to_dict()))) == item
