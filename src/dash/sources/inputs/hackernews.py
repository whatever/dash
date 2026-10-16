"""`hackernews:<url>` sources: one item per story on a Hacker News listing page."""

import re
from urllib.parse import urljoin

from dash.sources.common import Item, plain
from dash.sources.inputs.web import Web

STORY = re.compile(
    r'<tr class="athing[^"]*" id="(?P<id>\d+)".*?<span class="titleline">'
    r'<a href="(?P<href>[^"]+)"[^>]*>'
    r"(?P<title>.*?)</a>(?P<rest>.*?)(?=<tr class=\"athing|$)",
    flags=re.S,
)
SCORE = re.compile(r'<span class="score"[^>]*>(\d+) points?</span>')
AGE = re.compile(r'<span class="age" title="([^" ]+)')
COMMENTS = re.compile(r">(\d+)(?:&nbsp;|\s)comments?</a>")


def parse_hackernews(source: str, url: str, body: str) -> list[Item]:
    """Return the stories on a Hacker News page (front page, /newest, /ask, ...)."""
    items: list[Item] = []
    for m in STORY.finditer(body):
        story = f"https://news.ycombinator.com/item?id={m['id']}"
        rest = m["rest"]
        score, age, comments = SCORE.search(rest), AGE.search(rest), COMMENTS.search(rest)
        meta = [
            f"{score[1]} points" if score else "",
            f"{comments[1]} comments" if comments else "",
        ]
        link = urljoin(url, m["href"])
        summary = " · ".join(x for x in meta if x)
        if link != story:
            summary = f"{summary} · discussion {story}" if summary else f"discussion {story}"
        items.append(
            Item(
                source=source,
                key=m["id"],
                title=plain(m["title"], 300),
                url=link,
                summary=summary,
                published=age[1] if age else "",
            )
        )
    return items


class HackerNews(Web):
    """A Hacker News listing; each story is its own item, seen once."""

    kind = "hackernews"

    def parse(self, body: str) -> list[Item]:
        return parse_hackernews(str(self), self.target, body)
