from __future__ import annotations

from datetime import datetime

from PIL import Image

from ..config import Item, Settings
from ..domain import Rect, SlotAssignment
from ..selection import RandomSelector, select_scheduled
from ..typography import render_centered_text


class ItemsModule:
    name = "items"

    def __init__(self, random_selector: RandomSelector | None = None) -> None:
        self.random_selector = random_selector or RandomSelector()

    def prepare(
        self,
        settings: Settings,
        at: datetime,
        assignment: SlotAssignment,
    ) -> int:
        selected_mode = assignment.option("mode", settings.mode)
        if selected_mode == "scheduled":
            return select_scheduled(settings, at.time()).id
        if selected_mode == "random":
            return self.random_selector.select(settings).id
        raise ValueError(f"unknown items mode: {selected_mode}")

    def remember(self, content_id: int) -> None:
        self.random_selector.remember(content_id)

    @staticmethod
    def resolve(settings: Settings, content_id: int) -> Item:
        for item in settings.items:
            if item.id == content_id:
                return item
        raise ValueError(f"unknown item id: {content_id}")

    def render(
        self,
        settings: Settings,
        content_id: int | str,
        rect: Rect,
        now: datetime,
    ) -> Image.Image:
        if type(content_id) is not int:
            raise ValueError(f"invalid items content id: {content_id}")
        item = self.resolve(settings, content_id)
        return render_centered_text(
            item.text,
            settings.font,
            settings.latin_font,
            (rect.width, rect.height),
        )
