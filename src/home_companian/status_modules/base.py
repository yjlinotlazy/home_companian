from __future__ import annotations

from datetime import datetime
from typing import Protocol

from PIL import Image

from ..config import Settings
from ..domain import StatusAssignment


class StatusModule(Protocol):
    name: str

    def render(
        self,
        settings: Settings,
        at: datetime,
        assignment: StatusAssignment,
    ) -> Image.Image:
        """Render one tightly sized status-bar tile."""
