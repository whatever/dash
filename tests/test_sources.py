import json
from typing import cast

import fakeredis
import httpx
import pytest
from click.testing import CliRunner

import dash
from dash.db import Store
from dash.queue import JOBS, UPDATE, Job, Queue
from dash.sources.common import Item, Source, plain
from dash.sources.inputs.bushwick import BushwickDaily
from dash.sources.inputs.hackernews import HackerNews
from dash.sources.inputs.web import Web, parse_page
from dash.sources.scrape import scrape
from dash.worker import Worker
from tests.fakes import FakeChat, FakeEmbedder, FakeExtractor, FakeStore

PAGE = "<html><title>Status</title><script>x()</script><body>All &amp; good</body></html>"


def page_items(source: Source) -> list[Item]:
    return parse_page(str(source), source.target, PAGE)


def test_source_parse() -> None:
    assert Source.parse(" web:https://s/ ") == Source("web", "https://s/")
    assert str(Source.parse("web:https://s/")) == "web:https://s/"
    for bad in ("nope", "rss:https://x/feed", "web:"):
        with pytest.raises(ValueError, match="Bad source"):
            Source.parse(bad)


def test_plain_strips_tags_and_truncates() -> None:
    assert plain("<p>a  &amp;\n b</p>") == "a & b"
    assert plain("abcdef", 4) == "abc…"


def test_parse_page_key_changes_with_text() -> None:
    (a,) = parse_page("web:u", "https://s/", PAGE)
    (b,) = parse_page("web:u", "https://s/", PAGE.replace("good", "bad"))
    assert a.title == "Status"
    assert a.summary == "Status All & good"
    assert a.key != b.key


async def test_fetch_gets_the_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://s/status"
        return httpx.Response(200, text=PAGE)

    web = Web("https://s/status", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    (item,) = await web.fetch()
    assert (item.source, item.url) == ("web:https://s/status", "https://s/status")


@pytest.fixture
def queue() -> Queue:
    return Queue(fakeredis.FakeAsyncRedis(decode_responses=True))


async def test_scrape_enqueues_only_new_items_and_survives_failures(queue: Queue) -> None:
    good, bad = Source.parse("web:https://ok/"), Source.parse("web:https://down/")

    async def fetcher(source: Source) -> list[Item]:
        if source == bad:
            raise httpx.ConnectError("down")
        return page_items(source)

    dry = await scrape([good, bad], queue, dry_run=True, fetcher=fetcher)
    assert len(dry.enqueued) == 1
    assert await queue.redis.xlen(JOBS) == 0

    first = await scrape([good, bad], queue, fetcher=fetcher)
    assert (first.found, len(first.enqueued)) == (1, 1)
    assert first.failed == {"web:https://down/": "down"}
    second = await scrape([good, bad], queue, fetcher=fetcher)
    assert (second.found, len(second.enqueued)) == (1, 0)

    await queue.ensure_group()
    job = await queue.claim("w", block_ms=10)
    assert job is not None
    assert job.kind == UPDATE
    assert job.data["title"] == "Status"


async def test_scrape_without_deduplicate_enqueues_every_time(
    queue: Queue, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Web, "deduplicate", False)
    source = Source.parse("web:https://ok/")

    async def fetcher(source: Source) -> list[Item]:
        return page_items(source)

    first = await scrape([source], queue, fetcher=fetcher)
    second = await scrape([source], queue, fetcher=fetcher)

    assert (len(first.enqueued), len(second.enqueued)) == (1, 1)
    assert await queue.redis.xlen(JOBS) == 2


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
    (item,) = page_items(Source.parse("web:https://s/"))
    await worker.handle(Job("1-0", "j1", kind=UPDATE, data=item.to_dict()))
    await worker.handle(Job("2-0", "j2", kind=UPDATE, data=item.to_dict()))

    assert [m.content for m in store.mems] == [item.text()]
    assert store.mems[0].source == "scrape"
    assert store.mems[0].tags == ["web", "web:https://s/"]
    assert [e async for e in queue.events("j2")] == [{"kind": "done", "stored": False}]


def test_cli_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)

    def from_url(url: str) -> Queue:
        return Queue(redis)

    monkeypatch.setattr(Queue, "from_url", from_url)

    async def fake_fetch(source: Source) -> list[Item]:
        return page_items(source)

    monkeypatch.setattr("dash.sources.scrape.fetch", fake_fetch)
    result = CliRunner().invoke(dash.main, ["scrape", "-s", "web:https://n/", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "new web:https://n/ Status" in result.output


def test_cli_needs_sources() -> None:
    result = CliRunner().invoke(
        dash.main, ["scrape"], env={"SCRAPE_SOURCES": "", "DATABASE_URL": ""}
    )
    assert result.exit_code == 2
    assert "No sources" in result.output
    bad = CliRunner().invoke(dash.main, ["scrape", "-s", "rss:x"])
    assert bad.exit_code == 2


def test_update_payload_round_trips() -> None:
    (item,) = page_items(Source.parse("web:https://s/"))
    assert Item.from_dict(json.loads(json.dumps(item.to_dict()))) == item


HN = (
    '<table><tr class="athing submission" id="1"><td class="title"><span class="titleline">'
    '<a href="https://ex.com/a">A &amp; B</a></span></td></tr><tr><td class="subtext">'
    '<span class="score" id="score_1">12 points</span> '
    '<span class="age" title="2026-10-15T23:37:42">'
    '<a href="item?id=1">1 hour ago</a></span> | <a href="item?id=1">3&nbsp;comments</a></td></tr>'
    '<tr class="athing submission" id="2"><td class="title"><span class="titleline">'
    '<a href="item?id=2">Ask HN: x?</a></span></td></tr></table>'
)

BUSHWICK = (
    '<article class="top-lede"><a href="/news/a/"><img alt="x"></a>'
    '<h2 class="t"><a href="https://bushwickdaily.com/news/a/">Bar opens</a></h2>'
    '<p class="lede-excerpt">A new <b>bar</b>.</p></article>'
    '<article class="margin-teaser">'
    '<h3><a href="https://bushwickdaily.com/news/a/">Bar opens</a></h3></article>'
    '<article class="ad">no headline</article>'
)


def mock(body: str):
    return lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text=body))
    )


def test_site_kinds_parse() -> None:
    assert Source.parse("hackernews:https://news.ycombinator.com/").kind == "hackernews"
    assert Source.parse("bushwick:https://bushwickdaily.com/").kind == "bushwick"


async def test_hackernews_one_item_per_story() -> None:
    a, b = await HackerNews("https://news.ycombinator.com/", mock(HN)).fetch()
    assert isinstance(HackerNews("u"), Web)
    assert (a.key, a.title, a.url, a.published) == (
        "1",
        "A & B",
        "https://ex.com/a",
        "2026-10-15T23:37:42",
    )
    assert a.summary == "12 points · 3 comments · discussion https://news.ycombinator.com/item?id=1"
    assert a.source == "hackernews:https://news.ycombinator.com/"
    assert (b.key, b.url, b.summary) == ("2", "https://news.ycombinator.com/item?id=2", "")


async def test_bushwick_one_item_per_article() -> None:
    (a,) = await BushwickDaily("https://bushwickdaily.com/", mock(BUSHWICK)).fetch()
    assert isinstance(BushwickDaily("u"), Web)
    assert (a.key, a.title, a.summary) == (
        "https://bushwickdaily.com/news/a/",
        "Bar opens",
        "A new bar .",
    )
