from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Any

import yaml

from .domain import PanelConfig, SlotAssignment, StatusAssignment, StatusBarConfig


DEFAULT_CONFIG_PATH = Path("~/.config/home_companian/config.yaml").expanduser()
ITEM_TYPES = {"personal", "family_task"}


class ConfigError(ValueError):
    """Raised when the user configuration is missing or invalid."""


@dataclass(frozen=True)
class Item:
    id: int
    type: str
    text: str


@dataclass(frozen=True)
class ScheduleEntry:
    time: time
    item_id: int


@dataclass(frozen=True)
class FontChoice:
    name: str
    path: Path


@dataclass(frozen=True)
class ChannelConfig:
    id: str
    mode: str
    schedule: tuple[ScheduleEntry, ...]
    random_items: tuple[int, ...]


@dataclass(frozen=True)
class RefreshConfig:
    minutes: int
    active_start: time
    active_end: time


@dataclass(frozen=True)
class PresentationConfig:
    panel: PanelConfig
    status_bar: StatusBarConfig


@dataclass(frozen=True)
class DeviceConfig:
    id: str
    profile: str
    channel: str
    refresh: RefreshConfig
    presentation: PresentationConfig


@dataclass(frozen=True)
class Settings:
    """Fully resolved settings for one device instance."""

    device_id: str
    profile_id: str
    channel_id: str
    mode: str
    font: Path
    fonts: tuple[FontChoice, ...]
    latin_font: Path
    latin_fonts: tuple[FontChoice, ...]
    library_dir: Path
    refresh_minutes: int
    active_start: time
    active_end: time
    items: tuple[Item, ...]
    schedule: tuple[ScheduleEntry, ...]
    random_items: tuple[int, ...]
    panel: PanelConfig
    status_bar: StatusBarConfig


@dataclass(frozen=True)
class Config:
    """Global configuration before selecting a device instance."""

    font: Path
    fonts: tuple[FontChoice, ...]
    latin_font: Path
    latin_fonts: tuple[FontChoice, ...]
    library_dir: Path
    items: tuple[Item, ...]
    channels: tuple[ChannelConfig, ...]
    devices: tuple[DeviceConfig, ...]
    default_device: str

    def for_device(self, device_id: str) -> Settings:
        device = next(
            (candidate for candidate in self.devices if candidate.id == device_id),
            None,
        )
        if device is None:
            raise ConfigError(f"unknown device: {device_id}")
        channel = next(
            (candidate for candidate in self.channels if candidate.id == device.channel),
            None,
        )
        if channel is None:
            raise ConfigError(
                f"device {device.id} references unknown channel: {device.channel}"
            )
        return Settings(
            device_id=device.id,
            profile_id=device.profile,
            channel_id=channel.id,
            mode=channel.mode,
            font=self.font,
            fonts=self.fonts,
            latin_font=self.latin_font,
            latin_fonts=self.latin_fonts,
            library_dir=self.library_dir,
            refresh_minutes=device.refresh.minutes,
            active_start=device.refresh.active_start,
            active_end=device.refresh.active_end,
            items=self.items,
            schedule=channel.schedule,
            random_items=channel.random_items,
            panel=device.presentation.panel,
            status_bar=device.presentation.status_bar,
        )


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{label} must be a mapping")
    return value


def _required_text(mapping: dict[str, Any], key: str, label: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{label}.{key} must be non-empty text")
    return value.strip()


def _required_item_id(mapping: dict[str, Any], key: str, label: str) -> int:
    value = mapping.get(key)
    if type(value) is not int or value <= 0:
        raise ConfigError(f"{label}.{key} must be a positive integer")
    return value


def _configured_path(value: Any, key: str, config_path: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{key} must be configured")
    configured = Path(value).expanduser()
    if not configured.is_absolute():
        configured = config_path.parent / configured
    return configured.resolve()


def _config_time(value: Any, key: str, default: str) -> time:
    raw = default if value is None else value
    if not isinstance(raw, str):
        raise ConfigError(f"{key} must use HH:MM")
    try:
        return datetime.strptime(raw, "%H:%M").time()
    except ValueError as exc:
        raise ConfigError(f"{key} must use HH:MM") from exc


def _load_fonts(
    root: dict[str, Any],
    key: str,
    font: Path,
    config_path: Path,
) -> tuple[FontChoice, ...]:
    raw_fonts = root.get(key)
    if raw_fonts is None:
        return (FontChoice(font.stem, font),)
    if not isinstance(raw_fonts, dict) or not raw_fonts:
        raise ConfigError(f"{key} must be a non-empty mapping of names to paths")

    fonts: list[FontChoice] = []
    for raw_name, raw_path in raw_fonts.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ConfigError("font names must be non-empty text")
        path = _configured_path(raw_path, f"{key}.{raw_name}", config_path)
        fonts.append(FontChoice(raw_name.strip(), path))
    if font not in {choice.path for choice in fonts}:
        raise ConfigError(f"selected font must match one of the paths in {key}")
    return tuple(fonts)


def _load_items(library_dir: Path) -> tuple[Item, ...]:
    path = library_dir / "items.csv"
    try:
        handle = path.open(encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise ConfigError(f"items file cannot be opened: {path}") from exc

    try:
        with handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != ["id", "type", "text"]:
                raise ConfigError("items.csv columns must be exactly: id,type,text")

            items: list[Item] = []
            seen_ids: set[int] = set()
            for row in reader:
                line = reader.line_num
                if None in row or any(value is None for value in row.values()):
                    raise ConfigError(f"items.csv line {line}: expected exactly 3 columns")
                try:
                    item_id = int(row["id"])
                except (TypeError, ValueError) as exc:
                    raise ConfigError(f"items.csv line {line}: id must be a positive integer") from exc
                if item_id <= 0:
                    raise ConfigError(f"items.csv line {line}: id must be a positive integer")
                if item_id in seen_ids:
                    raise ConfigError(f"duplicate item id: {item_id}")

                item_type = (row["type"] or "").strip()
                if item_type not in ITEM_TYPES:
                    raise ConfigError(
                        f"items.csv line {line}: type must be personal or family_task"
                    )
                text = (row["text"] or "").strip()
                if not text:
                    raise ConfigError(f"items.csv line {line}: text must not be empty")

                seen_ids.add(item_id)
                items.append(Item(item_id, item_type, text))
    except csv.Error as exc:
        raise ConfigError(f"invalid CSV in {path}: {exc}") from exc

    if not items:
        raise ConfigError("items.csv must contain at least one item")
    return tuple(items)


def _load_panel(root: dict[str, Any]) -> PanelConfig:
    raw_panel = root.get(
        "panel",
        {"template": "landscape_1", "slots": {1: {"module": "items"}}},
    )
    panel = _mapping(raw_panel, "panel")
    template = _required_text(panel, "template", "panel")
    raw_slots = panel.get("slots")
    if not isinstance(raw_slots, dict):
        raise ConfigError("panel.slots must be a mapping")

    slots: list[SlotAssignment] = []
    for slot_id, raw_assignment in raw_slots.items():
        if type(slot_id) is not int or slot_id <= 0:
            raise ConfigError("panel slot ids must be positive integers")
        assignment = _mapping(raw_assignment, f"panel.slots.{slot_id}")
        module = _required_text(assignment, "module", f"panel.slots.{slot_id}")
        options: list[tuple[str, str]] = []
        for key, value in assignment.items():
            if key == "module":
                continue
            if not isinstance(key, str) or not isinstance(value, str) or not value.strip():
                raise ConfigError(
                    f"panel.slots.{slot_id}.{key} must be non-empty text"
                )
            options.append((key, value.strip()))
        slots.append(SlotAssignment(slot_id, module, tuple(sorted(options))))
    return PanelConfig(template, tuple(sorted(slots, key=lambda slot: slot.slot_id)))


def _load_status_bar(root: dict[str, Any]) -> StatusBarConfig:
    raw_status_bar = root.get(
        "status_bar",
        {
            "left": [],
            "center": [{"module": "solar_term"}],
            "right": [{"module": "weekday"}],
        },
    )
    status_bar = _mapping(raw_status_bar, "status_bar")
    groups: dict[str, tuple[StatusAssignment, ...]] = {}
    for group in ("left", "center", "right"):
        raw_assignments = status_bar.get(group, [])
        if not isinstance(raw_assignments, list):
            raise ConfigError(f"status_bar.{group} must be a list")
        assignments: list[StatusAssignment] = []
        for index, raw_assignment in enumerate(raw_assignments):
            label = f"status_bar.{group}[{index}]"
            assignment = _mapping(raw_assignment, label)
            module = _required_text(assignment, "module", label)
            if module not in {"date", "solar_term", "time", "weekday"}:
                raise ConfigError(f"unknown status module: {module}")
            options: list[tuple[str, str]] = []
            for key, value in assignment.items():
                if key == "module":
                    continue
                if not isinstance(key, str) or not isinstance(value, str) or not value:
                    raise ConfigError(f"{label}.{key} must be text")
                options.append((key, value))
            assignments.append(StatusAssignment(module, tuple(sorted(options))))
        groups[group] = tuple(assignments)
    extra_groups = set(status_bar) - {"left", "center", "right"}
    if extra_groups:
        raise ConfigError(f"unknown status bar group: {sorted(extra_groups)[0]}")
    return StatusBarConfig(groups["left"], groups["center"], groups["right"])


def _load_channel(
    channel_id: str,
    raw: Any,
    item_ids: set[int],
) -> ChannelConfig:
    channel = _mapping(raw, f"channels.{channel_id}")
    mode = str(channel.get("mode", "scheduled"))
    if mode not in {"scheduled", "random"}:
        raise ConfigError(f"channels.{channel_id}.mode must be scheduled or random")

    raw_schedule = channel.get("schedule", [])
    raw_random_items = channel.get("random_items", [])
    if not isinstance(raw_schedule, list) or not all(
        isinstance(row, dict) for row in raw_schedule
    ):
        raise ConfigError(f"channels.{channel_id}.schedule must be a list of mappings")
    if not isinstance(raw_random_items, list) or not all(
        type(item) is int for item in raw_random_items
    ):
        raise ConfigError(
            f"channels.{channel_id}.random_items must be a list of item ids"
        )

    schedule: list[ScheduleEntry] = []
    seen_times: set[time] = set()
    for index, row in enumerate(raw_schedule):
        label = f"channels.{channel_id}.schedule[{index}]"
        raw_time = _required_text(row, "time", label)
        item_id = _required_item_id(row, "item", label)
        try:
            entry_time = datetime.strptime(raw_time, "%H:%M").time()
        except ValueError as exc:
            raise ConfigError(f"{label}.time must use HH:MM") from exc
        if entry_time in seen_times:
            raise ConfigError(f"duplicate schedule time: {raw_time}")
        if item_id not in item_ids:
            raise ConfigError(f"{label} references unknown item: {item_id}")
        seen_times.add(entry_time)
        schedule.append(ScheduleEntry(entry_time, item_id))

    random_items = tuple(raw_random_items)
    unknown_random_ids = [item_id for item_id in random_items if item_id not in item_ids]
    if unknown_random_ids:
        raise ConfigError(
            f"channels.{channel_id}.random_items references unknown item: "
            f"{unknown_random_ids[0]}"
        )
    if not schedule:
        raise ConfigError(f"channels.{channel_id}.schedule must not be empty")
    if not random_items:
        raise ConfigError(f"channels.{channel_id}.random_items must not be empty")
    if len(set(random_items)) != len(random_items):
        raise ConfigError(
            f"channels.{channel_id}.random_items must not contain duplicate ids"
        )
    return ChannelConfig(
        channel_id,
        mode,
        tuple(sorted(schedule, key=lambda entry: entry.time)),
        random_items,
    )


def _load_device(
    device_id: str,
    raw: Any,
    channel_ids: set[str],
) -> DeviceConfig:
    from .devices import get_device_profile

    device = _mapping(raw, f"devices.{device_id}")
    profile = _required_text(device, "profile", f"devices.{device_id}")
    try:
        get_device_profile(profile)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    channel = _required_text(device, "channel", f"devices.{device_id}")
    if channel not in channel_ids:
        raise ConfigError(f"device {device_id} references unknown channel: {channel}")

    refresh = _mapping(device.get("refresh"), f"devices.{device_id}.refresh")
    minutes = refresh.get("minutes")
    if not isinstance(minutes, int) or minutes <= 0:
        raise ConfigError(f"devices.{device_id}.refresh.minutes must be positive")
    active_start = _config_time(
        refresh.get("active_start"),
        f"devices.{device_id}.refresh.active_start",
        "07:00",
    )
    active_end = _config_time(
        refresh.get("active_end"),
        f"devices.{device_id}.refresh.active_end",
        "22:00",
    )
    if active_start >= active_end:
        raise ConfigError(
            f"devices.{device_id}.refresh.active_start must be earlier than active_end"
        )

    presentation = _mapping(
        device.get("presentation"),
        f"devices.{device_id}.presentation",
    )
    return DeviceConfig(
        id=device_id,
        profile=profile,
        channel=channel,
        refresh=RefreshConfig(minutes, active_start, active_end),
        presentation=PresentationConfig(
            panel=_load_panel(presentation),
            status_bar=_load_status_bar(presentation),
        ),
    )


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc

    root = _mapping(raw, "config")
    library_dir = _configured_path(root.get("library_dir"), "library_dir", path)
    items = _load_items(library_dir)
    item_ids = {item.id for item in items}

    font = _configured_path(root.get("font"), "font", path)
    fonts = _load_fonts(root, "fonts", font, path)
    latin_font = _configured_path(root.get("latin_font", root.get("font")), "latin_font", path)
    latin_fonts = _load_fonts(root, "latin_fonts", latin_font, path)

    raw_channels = _mapping(root.get("channels"), "channels")
    if not raw_channels:
        raise ConfigError("channels must not be empty")
    channels = tuple(
        _load_channel(str(channel_id), raw_channel, item_ids)
        for channel_id, raw_channel in raw_channels.items()
    )
    raw_devices = _mapping(root.get("devices"), "devices")
    if not raw_devices:
        raise ConfigError("devices must not be empty")
    devices = tuple(
        _load_device(str(device_id), raw_device, {channel.id for channel in channels})
        for device_id, raw_device in raw_devices.items()
    )
    default_device = _required_text(root, "default_device", "config")
    if default_device not in {device.id for device in devices}:
        raise ConfigError(f"default_device references unknown device: {default_device}")

    return Config(
        font=font,
        fonts=fonts,
        latin_font=latin_font,
        latin_fonts=latin_fonts,
        library_dir=library_dir,
        items=items,
        channels=channels,
        devices=devices,
        default_device=default_device,
    )
