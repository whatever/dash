"""Fetching web pages for the agent, refusing any address inside the network."""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

from dash.sources.common import plain

MAX_BYTES = 1_000_000
MAX_CHARS = 20_000
MAX_REDIRECTS = 5

Resolve = Callable[[str, int], Awaitable[list[str]]]


class RefusedError(Exception):
    """A URL the agent may not fetch."""


async def resolve(host: str, port: int) -> list[str]:
    """Return every address the given host resolves to."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


def is_public(address: str) -> bool:
    """Return True if the given address is reachable on the public internet."""
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


@dataclass(frozen=True)
class Fetcher:
    """Fetches pages through the given client, checking each hop's address first."""

    client: httpx.AsyncClient
    resolve: Resolve = resolve

    async def check(self, url: httpx.URL) -> None:
        """Raise RefusedError unless the URL is http(s) and resolves only to public addresses."""
        if url.scheme not in ("http", "https") or not url.host:
            raise RefusedError(f"only http and https URLs can be fetched, not {url}")
        port = url.port or (443 if url.scheme == "https" else 80)
        addresses = await self.resolve(url.host, port)
        if not addresses or not all(is_public(a) for a in addresses):
            raise RefusedError(f"{url.host} resolves to an address inside the network")

    async def fetch(self, url: str) -> str:
        """Return the status, final URL and text of the given page."""
        target = httpx.URL(url)
        for _ in range(MAX_REDIRECTS + 1):
            await self.check(target)
            async with self.client.stream("GET", target, follow_redirects=False) as response:
                if response.is_redirect and "location" in response.headers:
                    target = target.join(response.headers["location"])
                    continue
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) >= MAX_BYTES:
                        break
                text = bytes(body[:MAX_BYTES]).decode(response.encoding or "utf-8", "replace")
                kind = response.headers.get("content-type", "")
                text = plain(text, MAX_CHARS) if "html" in kind else text[:MAX_CHARS]
                return f"{response.status_code} {target}\n\n{text}"
        raise RefusedError(f"more than {MAX_REDIRECTS} redirects")
