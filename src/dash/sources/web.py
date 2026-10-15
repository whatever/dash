"""`web:<url>` sources: one page, and a new item whenever its visible text changes."""

import asyncio
import hashlib
import logging
import re
from collections.abc import Awaitable, Callable, Sequence

import httpx

from dash.queue import Queue
from dash.sources.common import SUMMARY_CHARS, Item, Report, Source, client, plain

log = logging.getLogger(__name__)

Fetch = Callable[[Source, httpx.AsyncClient], Awaitable[list[Item]]]


def parse_page(source: str, url: str, body: str) -> list[Item]:
    match = re.search(r"<title[^>]*>(.*?)</title>", body, flags=re.S | re.I)
    title = plain(match.group(1), 300) if match else url
    text = plain(body, 1_000_000)
    digest = hashlib.sha256(text.encode()).hexdigest()[:16]
    return [Item(source=source, key=digest, title=title, url=url, summary=text[:SUMMARY_CHARS])]


async def fetch(source: Source, http: httpx.AsyncClient) -> list[Item]:
    response = await http.get(source.target)
    response.raise_for_status()
    return parse_page(str(source), source.target, response.text)


async def scrape(
    sources: Sequence[Source],
    queue: Queue,
    *,
    dry_run: bool = False,
    fetcher: Fetch | None = None,
    http: httpx.AsyncClient | None = None,
) -> Report:
    report = Report()
    own = http is None
    http = http or client()
    try:
        results = await asyncio.gather(
            *((fetcher or fetch)(s, http) for s in sources), return_exceptions=True
        )
    finally:
        if own:
            await http.aclose()
    for source, result in zip(sources, results, strict=True):
        if isinstance(result, BaseException):
            log.warning("source %s failed: %s", source, result)
            report.failed[str(source)] = str(result) or type(result).__name__
            continue
        report.found += len(result)
        for item in result:
            if dry_run:
                if not await queue.seen(item):
                    report.enqueued.append(item)
            elif await queue.mark_seen(item):
                await queue.enqueue_update(item.to_dict())
                report.enqueued.append(item)
    return report


async def run(sources: Sequence[Source], redis_url: str, *, dry_run: bool) -> Report:
    queue = Queue.from_url(redis_url)
    try:
        return await scrape(sources, queue, dry_run=dry_run)
    finally:
        await queue.close()
