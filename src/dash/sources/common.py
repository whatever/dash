import html
import re
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

USER_AGENT = "dash/0.1 (+https://github.com/whatever/dash)"
TIMEOUT_SECONDS = 20
SUMMARY_CHARS = 1000


@dataclass(frozen=True)
class Source:
    kind: str
    target: str

    @classmethod
    def parse(cls, spec: str) -> "Source":
        from dash.sources.inputs import KINDS

        kind, sep, target = spec.strip().partition(":")
        if not sep or kind not in KINDS or not target:
            raise ValueError(f"Bad source {spec!r}: want one of {', '.join(KINDS)} then ':'.")
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
        when = f" ({self.published})" if self.published else ""
        body = f": {self.summary}" if self.summary else ""
        return f"[{self.source}]{when} {self.title}{body} <{self.url}>"


@dataclass
class Report:
    found: int = 0
    enqueued: list[Item] = field(default_factory=list[Item])
    failed: dict[str, str] = field(default_factory=dict[str, str])


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_SECONDS,
        follow_redirects=True,
    )


def plain(text: str, limit: int = SUMMARY_CHARS) -> str:
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", text, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
