from __future__ import annotations

from datetime import datetime
from typing import Mapping

from PIL import Image

from .config import ConfigError, Settings
from .domain import PreparedPanel
from .modules import Module
from .rendering import CONTENT_HEIGHT, HEIGHT, STATUS_BAR_HEIGHT, VISIBLE_WIDTH
from .status_bar import render_status_bar
from .status_modules import StatusModule
from .templates import load_template


def render_panel(
    panel: PreparedPanel,
    settings: Settings,
    now: datetime,
    content_modules: Mapping[str, Module],
    status_modules: Mapping[str, StatusModule],
) -> Image.Image:
    template = load_template(panel.template)
    if (template.width, template.height) != (VISIBLE_WIDTH, CONTENT_HEIGHT):
        raise ConfigError(
            f"template {template.id} must be {VISIBLE_WIDTH}x{CONTENT_HEIGHT}"
        )
    image = Image.new("1", (VISIBLE_WIDTH, HEIGHT), 255)
    image.paste(render_status_bar(settings, now, status_modules), (0, 0))
    for prepared in panel.slots:
        try:
            rect = template.slot(prepared.slot_id)
        except KeyError as exc:
            raise ConfigError(
                f"template {template.id} has no slot {prepared.slot_id}"
            ) from exc
        module = content_modules.get(prepared.module)
        if module is None:
            raise ConfigError(f"unknown module: {prepared.module}")
        tile = module.render(settings, prepared.content_id, rect, now)
        image.paste(tile, (rect.x, rect.y + STATUS_BAR_HEIGHT))
    return image
