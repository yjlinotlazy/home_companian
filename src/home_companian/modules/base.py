from __future__ import annotations

from datetime import datetime
from typing import Protocol

from PIL import Image

from ..config import Settings
from ..domain import Rect, SlotAssignment


class Module(Protocol):
    name: str

    def prepare(
        self,
        settings: Settings,
        at: datetime,
        assignment: SlotAssignment,
    ) -> int | str:
        """Choose content without rendering it."""

    def render(
        self,
        settings: Settings,
        content_id: int | str,
        rect: Rect,
        now: datetime,
    ) -> Image.Image:
        """Render prepared content inside the supplied rectangle."""
