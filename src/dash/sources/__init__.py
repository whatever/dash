"""Real-world updates: fetch news feeds, subreddits and web pages as `Item`s.

Plain async functions with no knowledge of the CLI, cron or queue. `dash scrape`
fetches every configured source, drops items it has already seen and enqueues
the rest as `update` jobs for the worker.

A source is a spec string:

    rss:https://example.com/feed.xml   RSS or Atom feed
    reddit:python                      newest posts in r/python
    web:https://example.com/status     one page; an item whenever its text changes
"""

import hashlib
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from typing import Any

import httpx

USER_AGENT = "dash/0.1 (+https://github.com/whatever/dash)"
TIMEOUT_SECONDS = 20
SUMMARY_CHARS = 1000
KINDS = ("rss", "reddit", "web")


@dataclass(frozen=True)
class Source:
    kind: str
    target: str

    @classmethod
    def parse(cls, spec: str) -> "Source":
        kind, sep, target = spec.strip().partition(":")
        if not sep or kind not in KINDS or not target:
            raise ValueError(f"Bad source {spec!r}: want one of {', '.join(KINDS)} then ':'.")
        if kind == "reddit":
            target = target.removeprefix("r/")
        return cls(kind, target)

    def __str__(self) -> str:
        return f"{self.kind}:{self.target}"


@dataclass(frozen=True)
class Item:
    source: str
    # Stable per item within a source; used to skip items already enqueued.
    key: str
    title: str
    url: str
    summary: str = ""
    published: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Item":
        return cls(**{k: str(data.get(k, "")) for k in cls.__dataclass_fields__})

    def text(self) -> str:
        """One line for memory: what happened, where, and when."""
        when = f" ({self.published})" if self.published else ""
        body = f": {self.summary}" if self.summary else ""
        return f"[{self.source}]{when} {self.title}{body} <{self.url}>"


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_SECONDS,
        follow_redirects=True,
    )


def plain(text: str, limit: int = SUMMARY_CHARS) -> str:
    """Strip tags and squash whitespace."""
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", text, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(node: ET.Element, *names: str) -> ET.Element | None:
    for child in node:
        if _local(child.tag) in names:
            return child
    return None


def _text(node: ET.Element, *names: str) -> str:
    child = _child(node, *names)
    return (child.text or "").strip() if child is not None else ""


def parse_feed(source: str, body: str | bytes) -> list[Item]:
    """RSS 2.0 `<item>`s or Atom `<entry>`s, in document order."""
    root = ET.fromstring(body)  # noqa: S314 - expat >= 2.4 limits entity expansion
    items: list[Item] = []
    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        link = _text(node, "link")
        if not link:  # Atom puts the URL in an attribute.
            for child in node:
                if _local(child.tag) == "link" and child.get("rel", "alternate") == "alternate":
                    link = child.get("href", "")
                    break
        title = plain(_text(node, "title"), 300)
        key = _text(node, "guid", "id") or link or title
        if not key:
            continue
        items.append(
            Item(
                source=source,
                key=key,
                title=title or link,
                url=link,
                summary=plain(_text(node, "description", "summary", "content")),
                published=_text(node, "pubDate", "published", "updated"),
            )
        )
    return items


def parse_reddit(source: str, data: dict[str, Any]) -> list[Item]:
    items: list[Item] = []
    for child in data.get("data", {}).get("children", []):
        post = child.get("data", {})
        if post.get("stickied"):
            continue
        items.append(
            Item(
                source=source,
                key=str(post["name"]),
                title=plain(str(post.get("title", "")), 300),
                url="https://www.reddit.com" + str(post.get("permalink", "")),
                summary=plain(str(post.get("selftext", ""))),
                published=str(int(post.get("created_utc", 0)) or ""),
            )
        )
    return items


def parse_page(source: str, url: str, body: str) -> list[Item]:
    """One item keyed by a hash of the visible text, so a change makes a new item."""
    match = re.search(r"<title[^>]*>(.*?)</title>", body, flags=re.S | re.I)
    title = plain(match.group(1), 300) if match else url
    text = plain(body, 1_000_000)
    digest = hashlib.sha256(text.encode()).hexdigest()[:16]
    return [Item(source=source, key=digest, title=title, url=url, summary=text[:SUMMARY_CHARS])]


async def fetch(source: Source, http: httpx.AsyncClient) -> list[Item]:
    name = str(source)
    if source.kind == "rss":
        response = await http.get(source.target)
        response.raise_for_status()
        return parse_feed(name, response.content)
    if source.kind == "reddit":
        response = await http.get(
            f"https://www.reddit.com/r/{source.target}/new.json", params={"limit": 25}
        )
        response.raise_for_status()
        return parse_reddit(name, response.json())
    response = await http.get(source.target)
    response.raise_for_status()
    return parse_page(name, source.target, response.text)
