"""`atom:<url>` sources: one item per entry in an Atom feed."""

from xml.etree import ElementTree

from dash.sources.common import SUMMARY_CHARS, Item, plain
from dash.sources.inputs.web import Web

NS = "{http://www.w3.org/2005/Atom}"


def text_of(entry: ElementTree.Element, *names: str) -> str:
    """Return the first non-empty child text among the given Atom elements."""
    texts = (entry.findtext(f"{NS}{name}") or "" for name in names)
    return next((t.strip() for t in texts if t.strip()), "")


def link_of(entry: ElementTree.Element) -> str:
    """Return the entry's alternate link, or its first link."""
    links = entry.findall(f"{NS}link")
    alternate = [link for link in links if link.get("rel", "alternate") == "alternate"]
    return next((link.get("href", "") for link in alternate + links), "")


def parse_atom(source: str, body: str) -> list[Item]:
    """Return the entries of an Atom feed, each keyed by its id."""
    try:
        root = ElementTree.fromstring(body)  # noqa: S314 — expat 2.4.1+ blocks entity-expansion attacks
    except ElementTree.ParseError as err:
        raise ValueError(f"Not an Atom feed: {err}") from err
    return [
        Item(
            source=source,
            key=text_of(entry, "id") or link_of(entry),
            title=plain(text_of(entry, "title"), 300),
            url=link_of(entry),
            summary=plain(text_of(entry, "content", "summary"), SUMMARY_CHARS),
            published=text_of(entry, "published", "updated"),
        )
        for entry in root.iter(f"{NS}entry")
    ]


class Atom(Web):
    """An Atom feed; each entry is its own item, seen once."""

    kind = "atom"

    def parse(self, body: str) -> list[Item]:
        """Return the feed's entries as items."""
        return parse_atom(str(self), body)
