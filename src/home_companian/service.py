from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .config import DEFAULT_CONFIG_PATH, Item, load_settings
from .rendering import image_to_framebuffer, render_scene


@dataclass(frozen=True)
class RenderedDisplay:
    image: Image.Image
    framebuffer: bytes


class DisplayService:
    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH) -> None:
        self.config_path = config_path

    def render(self, battery: int | None = None) -> RenderedDisplay:
        settings = load_settings(self.config_path)
        item = self._select_item(settings.items)
        image = render_scene(item, settings.font, battery=battery)
        return RenderedDisplay(image=image, framebuffer=image_to_framebuffer(image))

    @staticmethod
    def _select_item(items: tuple[Item, ...]) -> Item:
        # M1 renders the first configured item. M2 replaces this with the
        # scheduled/random selector without changing the HTTP or render layers.
        return items[0]

