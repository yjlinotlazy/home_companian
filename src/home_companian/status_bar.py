from __future__ import annotations

from datetime import datetime
from typing import Mapping

from PIL import Image

from .config import ConfigError, Settings
from .domain import StatusAssignment
from .rendering import STATUS_BAR_HEIGHT, VISIBLE_WIDTH
from .status_modules import StatusModule


PADDING = 16
GAP = 12


def render_status_bar(
    settings: Settings,
    at: datetime,
    modules: Mapping[str, StatusModule],
) -> Image.Image:
    groups = {
        "left": _tiles(settings.status_bar.left, settings, at, modules),
        "center": _tiles(settings.status_bar.center, settings, at, modules),
        "right": _tiles(settings.status_bar.right, settings, at, modules),
    }
    widths = {name: _group_width(tiles) for name, tiles in groups.items()}
    starts = {
        "left": PADDING,
        "center": (VISIBLE_WIDTH - widths["center"]) // 2,
        "right": VISIBLE_WIDTH - PADDING - widths["right"],
    }
    spans = [
        (starts[name], starts[name] + widths[name], name)
        for name in ("left", "center", "right")
        if widths[name]
    ]
    if any(start < PADDING or end > VISIBLE_WIDTH - PADDING for start, end, _ in spans):
        raise ConfigError("status bar modules exceed the available width")
    for index, (start, end, name) in enumerate(spans):
        for other_start, other_end, other_name in spans[index + 1 :]:
            if start < other_end and other_start < end:
                raise ConfigError(f"status bar groups {name} and {other_name} overlap")

    image = Image.new("1", (VISIBLE_WIDTH, STATUS_BAR_HEIGHT), 255)
    for name in ("left", "center", "right"):
        x = starts[name]
        for tile in groups[name]:
            y = (STATUS_BAR_HEIGHT - tile.height) // 2
            image.paste(tile, (x, y))
            x += tile.width + GAP
    return image


def _tiles(
    assignments: tuple[StatusAssignment, ...],
    settings: Settings,
    at: datetime,
    modules: Mapping[str, StatusModule],
) -> tuple[Image.Image, ...]:
    result: list[Image.Image] = []
    for assignment in assignments:
        module = modules.get(assignment.module)
        if module is None:
            raise ConfigError(f"unknown status module: {assignment.module}")
        tile = module.render(settings, at, assignment)
        if tile.height > STATUS_BAR_HEIGHT:
            raise ConfigError(f"status module {assignment.module} is too tall")
        result.append(tile)
    return tuple(result)


def _group_width(tiles: tuple[Image.Image, ...]) -> int:
    return sum(tile.width for tile in tiles) + GAP * max(0, len(tiles) - 1)
