import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence

import httpx

from dash.queue import Queue
from dash.sources.common import Item, Report, Source, client
from dash.sources.inputs import INPUTS

log = logging.getLogger(__name__)

Fetch = Callable[[Source, httpx.AsyncClient], Awaitable[list[Item]]]


async def fetch(source: Source, http: httpx.AsyncClient) -> list[Item]:
    """Return the current items of the given source from its input kind."""
    return await INPUTS[source.kind].fetch(source.target, http)


async def scrape(
    sources: Sequence[Source],
    queue: Queue,
    *,
    dry_run: bool = False,
    fetcher: Fetch | None = None,
    http: httpx.AsyncClient | None = None,
) -> Report:
    """Fetch the given sources and enqueue their new items. Return what happened."""
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
        deduplicate = INPUTS[source.kind].deduplicate
        for item in result:
            if dry_run:
                if not deduplicate or not await queue.seen(item):
                    report.enqueued.append(item)
            elif not deduplicate or await queue.mark_seen(item):
                await queue.enqueue_update(item.to_dict())
                report.enqueued.append(item)
    return report


async def run(sources: Sequence[Source], redis_url: str, *, dry_run: bool) -> Report:
    """Scrape the given sources with a queue at the given Redis URL."""
    queue = Queue.from_url(redis_url)
    try:
        return await scrape(sources, queue, dry_run=dry_run)
    finally:
        await queue.close()
