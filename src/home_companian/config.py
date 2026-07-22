from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, time
from hashlib import sha256
from pathlib import Path
import random
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
class RefreshPeriod:
    start: time
    end: time
    minutes: int
    display_profile: str | None = None


@dataclass(frozen=True)
class RefreshConfig:
    minutes: int
    active_start: time
    active_end: time
    periods: tuple[RefreshPeriod, ...] = ()


@dataclass(frozen=True)
class RewardConfig:
    id: str
    name: str
    cost: int
    initial_points: int = 0


@dataclass(frozen=True)
class ChecklistGroup:
    id: str
    item_ids: tuple[int, ...]
    daily_limit: int | None = None

    def item_ids_for(self, day: date) -> tuple[int, ...]:
        if self.daily_limit is None:
            return self.item_ids
        seed = int.from_bytes(
            sha256(f"{self.id}:{day.isoformat()}".encode("utf-8")).digest()
        )
        selected = set(random.Random(seed).sample(self.item_ids, self.daily_limit))
        return tuple(item_id for item_id in self.item_ids if item_id in selected)


DEFAULT_REWARD = RewardConfig("toy", "玩具", 50, 25)


@dataclass(frozen=True)
class PresentationConfig:
    panels: tuple[PanelConfig, ...]
    status_bar: StatusBarConfig
    display_profiles: tuple[DisplayProfile, ...] = ()

    @property
    def panel(self) -> PanelConfig:
        return self.panels[0]


@dataclass(frozen=True)
class DisplayProfile:
    id: str
    minutes: int
    panels: tuple[PanelConfig, ...]


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
    panels: tuple[PanelConfig, ...]
    status_bar: StatusBarConfig
    refresh_periods: tuple[RefreshPeriod, ...] = ()
    display_profiles: tuple[DisplayProfile, ...] = ()
    reward: RewardConfig = DEFAULT_REWARD
    checklist_groups: tuple[ChecklistGroup, ...] = ()

    @property
    def panel(self) -> PanelConfig:
        return self.panels[0]

    def panels_at(self, at: datetime) -> tuple[PanelConfig, ...]:
        if not self.display_profiles:
            return self.panels
        selected_period = next(
            (
                period
                for period in self.refresh_periods
                if period.start <= at.time() < period.end
            ),
            None,
        )
        if (
            selected_period is None
            and self.refresh_periods
            and at.time() == self.refresh_periods[-1].end
        ):
            selected_period = self.refresh_periods[-1]
        if selected_period is None:
            selected_period = self.refresh_periods[0]
        return next(
            profile.panels
            for profile in self.display_profiles
            if profile.id == selected_period.display_profile
        )


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
    reward: RewardConfig = DEFAULT_REWARD
    checklist_groups: tuple[ChecklistGroup, ...] = ()

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
            panels=device.presentation.panels,
            status_bar=device.presentation.status_bar,
            refresh_periods=device.refresh.periods,
            display_profiles=device.presentation.display_profiles,
            reward=self.reward,
            checklist_groups=self.checklist_groups,
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


def _load_reward(root: dict[str, Any]) -> RewardConfig:
    raw_reward = root.get("reward")
    if raw_reward is None:
        return DEFAULT_REWARD
    reward = _mapping(raw_reward, "reward")
    reward_id = _required_text(reward, "id", "reward")
    name = _required_text(reward, "name", "reward")
    cost = reward.get("cost")
    if type(cost) is not int or cost <= 0:
        raise ConfigError("reward.cost must be a positive integer")
    initial_points = reward.get("initial_points", 0)
    if (
        type(initial_points) is not int
        or initial_points < 0
        or initial_points > cost
    ):
        raise ConfigError("reward.initial_points must be between 0 and reward.cost")
    return RewardConfig(reward_id, name, cost, initial_points)


def _load_checklist_groups(root: dict[str, Any]) -> tuple[ChecklistGroup, ...]:
    raw_groups = root.get("checklists")
    if raw_groups is None:
        return ()
    groups = _mapping(raw_groups, "checklists")
    configured: list[ChecklistGroup] = []
    assigned_ids: set[int] = set()
    for raw_group_id, raw_group in groups.items():
        if not isinstance(raw_group_id, str) or not raw_group_id.strip():
            raise ConfigError("checklist ids must be non-empty text")
        group_id = raw_group_id.strip()
        daily_limit = None
        if isinstance(raw_group, dict):
            extra_keys = set(raw_group) - {"items", "daily_limit"}
            if extra_keys:
                raise ConfigError(
                    f"checklists.{group_id} has unknown key: {sorted(extra_keys)[0]}"
                )
            raw_item_ids = raw_group.get("items")
            daily_limit = raw_group.get("daily_limit")
        else:
            raw_item_ids = raw_group
        if not isinstance(raw_item_ids, list) or not raw_item_ids:
            raise ConfigError(f"checklists.{group_id} must be a non-empty list")
        if not all(type(item_id) is int and item_id > 0 for item_id in raw_item_ids):
            raise ConfigError(
                f"checklists.{group_id} must contain positive integer item ids"
            )
        if len(set(raw_item_ids)) != len(raw_item_ids):
            raise ConfigError(f"checklists.{group_id} must not contain duplicate ids")
        if daily_limit is not None and (
            type(daily_limit) is not int
            or not 1 <= daily_limit <= len(raw_item_ids)
        ):
            raise ConfigError(
                f"checklists.{group_id}.daily_limit must be between 1 and item count"
            )
        duplicate = assigned_ids.intersection(raw_item_ids)
        if duplicate:
            raise ConfigError(
                f"checklist item {min(duplicate)} is assigned to multiple checklists"
            )
        assigned_ids.update(raw_item_ids)
        configured.append(
            ChecklistGroup(group_id, tuple(raw_item_ids), daily_limit)
        )
    return tuple(configured)


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


def _load_presentation(device_id: str, device: dict[str, Any]) -> PresentationConfig:
    label = f"devices.{device_id}.presentation"
    presentation = _mapping(device.get("presentation"), label)
    raw_display_profiles = presentation.get("display_profiles")
    raw_panels = presentation.get("panels")

    if raw_display_profiles is None:
        if raw_panels is None:
            panels = (_load_panel(presentation),)
        else:
            if not isinstance(raw_panels, list) or not raw_panels:
                raise ConfigError(f"{label}.panels must be a non-empty list")
            panels = tuple(
                _load_panel({"panel": raw_panel}) for raw_panel in raw_panels
            )
        display_profiles: tuple[DisplayProfile, ...] = ()
    else:
        if "panel" in presentation:
            raise ConfigError(
                f"{label}.display_profiles cannot be mixed with legacy panel"
            )
        panel_catalog = _mapping(raw_panels, f"{label}.panels")
        if not panel_catalog:
            raise ConfigError(
                f"{label}.panels must be a non-empty mapping when using display_profiles"
            )
        loaded_panels: dict[str, PanelConfig] = {}
        for raw_panel_id, raw_panel in panel_catalog.items():
            if not isinstance(raw_panel_id, str) or not raw_panel_id.strip():
                raise ConfigError(f"{label}.panel ids must be non-empty text")
            panel_id = raw_panel_id.strip()
            if panel_id in loaded_panels:
                raise ConfigError(f"duplicate {label}.panel id: {panel_id}")
            loaded_panels[panel_id] = _load_panel({"panel": raw_panel})

        profile_mapping = _mapping(
            raw_display_profiles,
            f"{label}.display_profiles",
        )
        if not profile_mapping:
            raise ConfigError(f"{label}.display_profiles must not be empty")
        loaded_profiles: list[DisplayProfile] = []
        for raw_profile_id, raw_profile in profile_mapping.items():
            if not isinstance(raw_profile_id, str) or not raw_profile_id.strip():
                raise ConfigError(f"{label}.display profile ids must be non-empty text")
            profile_id = raw_profile_id.strip()
            profile = _mapping(
                raw_profile,
                f"{label}.display_profiles.{profile_id}",
            )
            extra_keys = set(profile) - {"minutes", "panels"}
            if extra_keys:
                raise ConfigError(
                    f"{label}.display_profiles.{profile_id} has unknown key: "
                    f"{sorted(extra_keys)[0]}"
                )
            minutes = profile.get("minutes")
            if type(minutes) is not int or minutes <= 0:
                raise ConfigError(
                    f"{label}.display_profiles.{profile_id}.minutes must be positive"
                )
            panel_ids = profile.get("panels")
            if (
                not isinstance(panel_ids, list)
                or not panel_ids
                or not all(isinstance(panel_id, str) for panel_id in panel_ids)
            ):
                raise ConfigError(
                    f"{label}.display_profiles.{profile_id}.panels must be a non-empty list"
                )
            if len(set(panel_ids)) != len(panel_ids):
                raise ConfigError(
                    f"{label}.display_profiles.{profile_id}.panels must not contain duplicates"
                )
            unknown_panel_ids = [
                panel_id for panel_id in panel_ids if panel_id not in loaded_panels
            ]
            if unknown_panel_ids:
                raise ConfigError(
                    f"{label}.display_profiles.{profile_id} references unknown panel: "
                    f"{unknown_panel_ids[0]}"
                )
            loaded_profiles.append(
                DisplayProfile(
                    profile_id,
                    minutes,
                    tuple(loaded_panels[panel_id] for panel_id in panel_ids),
                )
            )
        panels = tuple(loaded_panels.values())
        display_profiles = tuple(loaded_profiles)

    return PresentationConfig(
        panels=panels,
        status_bar=_load_status_bar(presentation),
        display_profiles=display_profiles,
    )


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

    presentation_config = _load_presentation(device_id, device)
    display_profiles = {
        display_profile.id: display_profile
        for display_profile in presentation_config.display_profiles
    }

    refresh = _mapping(device.get("refresh"), f"devices.{device_id}.refresh")
    raw_periods = refresh.get("schedule")
    periods: tuple[RefreshPeriod, ...] = ()
    if raw_periods is None:
        if display_profiles:
            raise ConfigError(
                f"devices.{device_id}.refresh.schedule is required with display_profiles"
            )
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
    else:
        if any(key in refresh for key in ("minutes", "active_start", "active_end")):
            raise ConfigError(
                f"devices.{device_id}.refresh.schedule cannot be mixed with legacy fields"
            )
        if not isinstance(raw_periods, list) or not raw_periods:
            raise ConfigError(
                f"devices.{device_id}.refresh.schedule must be a non-empty list"
            )
        loaded_periods: list[RefreshPeriod] = []
        for index, raw_period in enumerate(raw_periods):
            label = f"devices.{device_id}.refresh.schedule[{index}]"
            period = _mapping(raw_period, label)
            start = _config_time(period.get("start"), f"{label}.start", "")
            end = _config_time(period.get("end"), f"{label}.end", "")
            if display_profiles:
                if "minutes" in period:
                    raise ConfigError(
                        f"{label}.minutes belongs in its display profile"
                    )
                display_profile_id = _required_text(period, "profile", label)
                try:
                    period_minutes = display_profiles[display_profile_id].minutes
                except KeyError as exc:
                    raise ConfigError(
                        f"{label} references unknown display profile: "
                        f"{display_profile_id}"
                    ) from exc
                extra_keys = set(period) - {"start", "end", "profile"}
            else:
                if "profile" in period:
                    raise ConfigError(
                        f"{label}.profile requires presentation.display_profiles"
                    )
                display_profile_id = None
                period_minutes = period.get("minutes")
                if not isinstance(period_minutes, int) or period_minutes <= 0:
                    raise ConfigError(f"{label}.minutes must be positive")
                extra_keys = set(period) - {"start", "end", "minutes"}
            if extra_keys:
                raise ConfigError(
                    f"{label} has unknown key: {sorted(extra_keys)[0]}"
                )
            duration_minutes = (
                datetime.combine(date.min, end) - datetime.combine(date.min, start)
            ).total_seconds() // 60
            if start >= end or duration_minutes % period_minutes != 0:
                raise ConfigError(
                    f"{label} must have start before end and divide evenly into minutes"
                )
            if loaded_periods and loaded_periods[-1].end != start:
                raise ConfigError(
                    f"{label}.start must equal the previous period end"
                )
            loaded_periods.append(
                RefreshPeriod(start, end, period_minutes, display_profile_id)
            )
        periods = tuple(loaded_periods)
        minutes = periods[0].minutes
        active_start = periods[0].start
        active_end = periods[-1].end

    return DeviceConfig(
        id=device_id,
        profile=profile,
        channel=channel,
        refresh=RefreshConfig(minutes, active_start, active_end, periods),
        presentation=presentation_config,
    )


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc

    root = _mapping(raw, "config")
    reward = _load_reward(root)
    checklist_groups = _load_checklist_groups(root)
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
        reward=reward,
        checklist_groups=checklist_groups,
    )
