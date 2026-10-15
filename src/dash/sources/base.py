from abc import ABC, abstractmethod
from typing import ClassVar

from dash.sources.common import Item


class InputSource(ABC):
    """A configured input that dash scrape checks for new items."""

    kind: ClassVar[str]
    deduplicate: ClassVar[bool] = True

    def __init__(self, target: str) -> None:
        self.target = target

    def __str__(self) -> str:
        return f"{self.kind}:{self.target}"

    @abstractmethod
    async def fetch(self) -> list[Item]:
        """Return the current items at the target."""
