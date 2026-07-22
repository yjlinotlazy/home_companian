from __future__ import annotations

from typing import Protocol

from PIL import Image

from ...config import Settings
from ...domain import Rect


class MathGame(Protocol):
    type: str

    def prepare(self) -> dict[str, object]:
        """Create a self-contained problem snapshot, including its hidden answer."""

    def render(
        self,
        snapshot: dict[str, object],
        settings: Settings,
        rect: Rect,
    ) -> Image.Image:
        """Validate and render a prepared snapshot without revealing its answer."""
