"""`bushwick:<url>` sources: one item per article teaser on a Bushwick Daily page."""

import re
from urllib.parse import urljoin

from dash.sources.common import Item, plain
from dash.sources.inputs.web import Web

ARTICLE = re.compile(r"<article\b[^>]*>(.*?)</article>", flags=re.S | re.I)
HEADLINE = re.compile(r'<h[1-4][^>]*>\s*<a href="([^"]+)"[^>]*>(.*?)</a>', flags=re.S | re.I)
EXCERPT = re.compile(r'<p class="[^"]*excerpt[^"]*"[^>]*>(.*?)</p>', flags=re.S | re.I)


def parse_bushwick(source: str, url: str, body: str) -> list[Item]:
    """Return the articles on a Bushwick Daily page, deduplicated by URL in page order."""
    items: dict[str, Item] = {}
    for block in ARTICLE.findall(body):
        headline = HEADLINE.search(block)
        if not headline:
            continue
        link = urljoin(url, headline[1])
        if link in items:
            continue
        excerpt = EXCERPT.search(block)
        items[link] = Item(
            source=source,
            key=link,
            title=plain(headline[2], 300),
            url=link,
            summary=plain(excerpt[1]) if excerpt else "",
        )
    return list(items.values())


class BushwickDaily(Web):
    """A Bushwick Daily front or section page; each article is its own item, seen once."""

    kind = "bushwick"

    def parse(self, body: str) -> list[Item]:
        return parse_bushwick(str(self), self.target, body)
