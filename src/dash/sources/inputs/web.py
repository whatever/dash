"""`web:<url>` sources: one page, and a new item whenever its visible text changes."""

import hashlib
import re
from collections.abc import Callable

import httpx

from dash.sources.base import InputSource
from dash.sources.common import SUMMARY_CHARS, Item, client, plain


def parse_page(source: str, url: str, body: str) -> list[Item]:
    """Return the page as one item whose key is a hash of its visible text."""
    match = re.search(r"<title[^>]*>(.*?)</title>", body, flags=re.S | re.I)
    title = plain(match.group(1), 300) if match else url
    text = plain(body, 1_000_000)
    digest = hashlib.sha256(text.encode()).hexdigest()[:16]
    return [Item(source=source, key=digest, title=title, url=url, summary=text[:SUMMARY_CHARS])]


class Web(InputSource):
    """A web page that changes when its visible text changes."""

    kind = "web"

    def __init__(self, http: Callable[[], httpx.AsyncClient] = client) -> None:
        self._http = http

    async def fetch(self, target: str) -> list[Item]:
        """Return the page at the given URL as one item."""
        async with self._http() as http:
            response = await http.get(target)
        response.raise_for_status()
        return parse_page(f"{self.kind}:{target}", target, response.text)
