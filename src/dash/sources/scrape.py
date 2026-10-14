"""Fetch sources and enqueue anything new. The body of `dash scrape`."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

import httpx

from dash.queue import Queue
from dash.sources import Item, Source, client, fetch

log = logging.getLogger(__name__)

Fetch = Callable[[Source, httpx.AsyncClient], Awaitable[list[Item]]]


@dataclass
class Report:
    found: int = 0
    enqueued: list[Item] = field(default_factory=list[Item])
    failed: dict[str, str] = field(default_factory=dict[str, str])


async def scrape(
    sources: Sequence[Source],
    queue: Queue,
    *,
    dry_run: bool = False,
    fetcher: Fetch | None = None,
    http: httpx.AsyncClient | None = None,
) -> Report:
    """Fetch every source concurrently; one failing source doesn't stop the others."""
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
