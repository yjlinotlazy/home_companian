from __future__ import annotations

from datetime import datetime
from typing import Mapping

from PIL import Image

from .config import ConfigError, Settings
from .domain import StatusAssignment
from .status_modules import StatusModule


PADDING = 16
GAP = 12


def render_status_bar(
    settings: Settings,
    at: datetime,
    modules: Mapping[str, StatusModule],
    width: int,
    height: int,
) -> Image.Image:
    groups = {
        "left": _tiles(settings.status_bar.left, settings, at, modules, height),
        "center": _tiles(settings.status_bar.center, settings, at, modules, height),
        "right": _tiles(settings.status_bar.right, settings, at, modules, height),
    }
    widths = {name: _group_width(tiles) for name, tiles in groups.items()}
    starts = {
        "left": PADDING,
        "center": (width - widths["center"]) // 2,
        "right": width - PADDING - widths["right"],
    }
    spans = [
        (starts[name], starts[name] + widths[name], name)
        for name in ("left", "center", "right")
        if widths[name]
    ]
    if any(start < PADDING or end > width - PADDING for start, end, _ in spans):
        raise ConfigError("status bar modules exceed the available width")
    for index, (start, end, name) in enumerate(spans):
        for other_start, other_end, other_name in spans[index + 1 :]:
            if start < other_end and other_start < end:
                raise ConfigError(f"status bar groups {name} and {other_name} overlap")

    image = Image.new("1", (width, height), 255)
    for name in ("left", "center", "right"):
        x = starts[name]
        for tile in groups[name]:
            y = (height - tile.height) // 2
            image.paste(tile, (x, y))
            x += tile.width + GAP
    return image


def _tiles(
    assignments: tuple[StatusAssignment, ...],
    settings: Settings,
    at: datetime,
    modules: Mapping[str, StatusModule],
    height: int,
) -> tuple[Image.Image, ...]:
    result: list[Image.Image] = []
    for assignment in assignments:
        module = modules.get(assignment.module)
        if module is None:
            raise ConfigError(f"unknown status module: {assignment.module}")
        tile = module.render(settings, at, assignment)
        if tile.height > height:
            raise ConfigError(f"status module {assignment.module} is too tall")
        result.append(tile)
    return tuple(result)


def _group_width(tiles: tuple[Image.Image, ...]) -> int:
    return sum(tile.width for tile in tiles) + GAP * max(0, len(tiles) - 1)
