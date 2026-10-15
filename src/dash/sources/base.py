from abc import ABC, abstractmethod
from typing import ClassVar

import httpx

from dash.sources.common import Item


class InputSource(ABC):
    """A kind of input that dash scrape checks for new items."""

    kind: ClassVar[str]
    deduplicate: ClassVar[bool] = True

    @abstractmethod
    async def fetch(self, target: str, http: httpx.AsyncClient) -> list[Item]:
        """Return the current items at the given target."""
