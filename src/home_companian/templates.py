from __future__ import annotations

from importlib import resources
from typing import Any

import yaml

from .config import ConfigError
from .domain import PanelConfig, Rect, Template


def load_template(template_id: str) -> Template:
    resource = resources.files("home_companian").joinpath(
        "template_data", f"{template_id}.yaml"
    )
    try:
        raw = yaml.safe_load(resource.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"unknown panel template: {template_id}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"invalid panel template: {template_id}")
    return _parse_template(raw, template_id)


def validate_panel(panel: PanelConfig) -> Template:
    template = load_template(panel.template)
    slot_ids = {slot_id for slot_id, _ in template.slots}
    for assignment in panel.slots:
        if assignment.slot_id not in slot_ids:
            raise ConfigError(
                f"template {template.id} has no slot {assignment.slot_id}"
            )
        if assignment.module not in {
            "items", "chinese", "images", "health", "math", "checklist"
        }:
            raise ConfigError(f"unknown module: {assignment.module}")
    return template


def _parse_template(raw: dict[str, Any], requested_id: str) -> Template:
    template_id = raw.get("id")
    size = raw.get("size")
    raw_slots = raw.get("slots")
    raw_lines = raw.get("lines", [])
    if template_id != requested_id:
        raise ConfigError(f"template id mismatch: {requested_id}")
    if not _integer_list(size, 2) or size[0] <= 0 or size[1] <= 0:
        raise ConfigError(f"template {template_id}.size must contain width and height")
    if not isinstance(raw_slots, dict) or not raw_slots:
        raise ConfigError(f"template {template_id}.slots must be a non-empty mapping")
    if not isinstance(raw_lines, list) or not all(
        _integer_list(line, 4) for line in raw_lines
    ):
        raise ConfigError(f"template {template_id}.lines must contain x1,y1,x2,y2 lists")

    width, height = size
    slots: list[tuple[int, Rect]] = []
    for slot_id, values in raw_slots.items():
        if type(slot_id) is not int or slot_id <= 0 or not _integer_list(values, 4):
            raise ConfigError(f"template {template_id} has an invalid slot")
        rect = Rect(*values)
        if (
            rect.x < 0
            or rect.y < 0
            or rect.width <= 0
            or rect.height <= 0
            or rect.x + rect.width > width
            or rect.y + rect.height > height
        ):
            raise ConfigError(f"template {template_id} slot {slot_id} is out of bounds")
        slots.append((slot_id, rect))
    for index, (slot_id, rect) in enumerate(slots):
        for other_id, other in slots[index + 1 :]:
            if _overlaps(rect, other):
                raise ConfigError(
                    f"template {template_id} slots {slot_id} and {other_id} overlap"
                )
    lines: list[tuple[int, int, int, int]] = []
    for line in raw_lines:
        x1, y1, x2, y2 = line
        if not all(
            (0 <= x1 < width, 0 <= x2 < width, 0 <= y1 < height, 0 <= y2 < height)
        ):
            raise ConfigError(f"template {template_id} line is out of bounds")
        lines.append((x1, y1, x2, y2))
    return Template(template_id, width, height, tuple(sorted(slots)), tuple(lines))


def _integer_list(value: Any, length: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) == length
        and all(type(item) is int for item in value)
    )


def _overlaps(first: Rect, second: Rect) -> bool:
    return not (
        first.x + first.width <= second.x
        or second.x + second.width <= first.x
        or first.y + first.height <= second.y
        or second.y + second.height <= first.y
    )
