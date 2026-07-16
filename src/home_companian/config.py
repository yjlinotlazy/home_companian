from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path("~/.config/home_companian/config.yaml").expanduser()


class ConfigError(ValueError):
    """Raised when the user configuration is missing or invalid."""


@dataclass(frozen=True)
class Item:
    id: str
    title: str
    description: str = ""


@dataclass(frozen=True)
class Settings:
    mode: str
    font: Path
    refresh_minutes: int
    items: tuple[Item, ...]
    schedule: tuple[dict[str, str], ...]
    random_items: tuple[str, ...]


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{label} must be a mapping")
    return value


def _required_text(mapping: dict[str, Any], key: str, label: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{label}.{key} must be non-empty text")
    return value.strip()


def load_settings(path: Path = DEFAULT_CONFIG_PATH) -> Settings:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc

    root = _mapping(raw, "config")
    raw_items = root.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ConfigError("items must be a non-empty list")

    items: list[Item] = []
    seen_ids: set[str] = set()
    for index, value in enumerate(raw_items):
        item_data = _mapping(value, f"items[{index}]")
        item_id = _required_text(item_data, "id", f"items[{index}]")
        if item_id in seen_ids:
            raise ConfigError(f"duplicate item id: {item_id}")
        seen_ids.add(item_id)
        items.append(
            Item(
                id=item_id,
                title=_required_text(item_data, "title", f"items[{index}]"),
                description=str(item_data.get("description", "")).strip(),
            )
        )

    mode = str(root.get("mode", "scheduled"))
    if mode not in {"scheduled", "random"}:
        raise ConfigError("mode must be scheduled or random")

    raw_font = root.get("font")
    if not isinstance(raw_font, str) or not raw_font.strip():
        raise ConfigError("font must be configured")
    font = Path(raw_font).expanduser()

    refresh_minutes = root.get("refresh_minutes", 60)
    if not isinstance(refresh_minutes, int) or refresh_minutes <= 0:
        raise ConfigError("refresh_minutes must be a positive integer")

    schedule = root.get("schedule", [])
    random_items = root.get("random_items", [])
    if not isinstance(schedule, list) or not all(isinstance(row, dict) for row in schedule):
        raise ConfigError("schedule must be a list of mappings")
    if not isinstance(random_items, list) or not all(isinstance(item, str) for item in random_items):
        raise ConfigError("random_items must be a list of item ids")

    return Settings(
        mode=mode,
        font=font,
        refresh_minutes=refresh_minutes,
        items=tuple(items),
        schedule=tuple(schedule),
        random_items=tuple(random_items),
    )
