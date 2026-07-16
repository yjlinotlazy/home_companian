from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
import math
from pathlib import Path
from threading import Lock
import os
import tempfile

import yaml

from PIL import Image

from .composition import render_panel
from .config import ConfigError, DEFAULT_CONFIG_PATH, Item, Settings, load_settings
from .domain import PreparedPanel, PreparedSlot
from .modules import (
    ChineseModule,
    HealthModule,
    ImagesModule,
    ItemsModule,
    MathModule,
    Module,
)
from .rendering import CONTENT_HEIGHT, VISIBLE_WIDTH, image_to_framebuffer
from .selection import RandomSelector, select_scheduled
from .status_modules import (
    DateModule,
    SolarTermModule,
    StatusModule,
    TimeModule,
    WeekdayModule,
)
from .templates import validate_panel


@dataclass(frozen=True)
class RenderedDisplay:
    item_id: int
    image: Image.Image
    framebuffer: bytes


class DisplayService:
    def __init__(
        self,
        config_path: Path = DEFAULT_CONFIG_PATH,
        current_display_path: Path | None = None,
    ) -> None:
        self.config_path = config_path
        self.current_display_path = current_display_path or Path(
            "~/.local/state/home_companian/current.png"
        ).expanduser()
        self.device_items_module = ItemsModule(RandomSelector())
        self.preview_items_module = ItemsModule(RandomSelector())
        self.device_modules: dict[str, Module] = {
            "items": self.device_items_module,
            "chinese": ChineseModule(),
            "images": ImagesModule(),
            "health": HealthModule(),
            "math": MathModule(),
        }
        self.preview_modules: dict[str, Module] = {
            "items": self.preview_items_module,
            "chinese": ChineseModule(),
            "images": ImagesModule(),
            "health": HealthModule(),
            "math": MathModule(),
        }
        self.status_modules: dict[str, StatusModule] = {
            "date": DateModule(),
            "solar_term": SolarTermModule(),
            "time": TimeModule(),
            "weekday": WeekdayModule(),
        }
        self._config_write_lock = Lock()
        self._next_panel_lock = Lock()
        self._next_panel: PreparedPanel | None = None
        self._next_panel_key: tuple[object, ...] | None = None
        self._next_panel_forced = False
        self._current_display_lock = Lock()
        self._current_display = self._load_current_display()

    def settings(self) -> Settings:
        settings = load_settings(self.config_path)
        template = validate_panel(settings.panel)
        if (template.width, template.height) != (VISIBLE_WIDTH, CONTENT_HEIGHT):
            raise ConfigError(
                f"selected template must be {VISIBLE_WIDTH}x{CONTENT_HEIGHT}"
            )
        return settings

    def render(
        self,
        preview_time: time | None = None,
        preview_random: bool = False,
        preview_item_id: int | None = None,
        device: bool = False,
        now: datetime | None = None,
    ) -> RenderedDisplay:
        settings = self.settings()
        now = now or datetime.now()
        display_now = now
        items = {item.id: item for item in settings.items}

        if preview_item_id is not None:
            if preview_item_id not in items:
                raise ValueError(f"unknown item id: {preview_item_id}")
            item = items[preview_item_id]
            if preview_time is not None:
                display_now = now.replace(
                    hour=preview_time.hour,
                    minute=preview_time.minute,
                    second=0,
                    microsecond=0,
                )
        elif preview_time is not None:
            display_now = now.replace(
                hour=preview_time.hour,
                minute=preview_time.minute,
                second=0,
                microsecond=0,
            )
            item = select_scheduled(settings, preview_time)
        elif preview_random:
            assignment = self._items_assignment(settings)
            random_assignment = type(assignment)(
                assignment.slot_id, assignment.module, (("mode", "random"),)
            )
            content_id = self.preview_items_module.prepare(settings, now, random_assignment)
            item = self.preview_items_module.resolve(settings, content_id)
        else:
            if device:
                forced_panel = self._consume_forced_panel(settings, now)
                if forced_panel is not None:
                    rendered = self._render_panel(forced_panel, settings, display_now)
                    self._remember_current(rendered)
                    return rendered
            if settings.mode == "scheduled":
                item = select_scheduled(settings, now.time())
            elif device:
                panel = self._consume_next_panel(settings, now)
                rendered = self._render_panel(panel, settings, display_now)
                self._remember_current(rendered)
                return rendered
            else:
                assignment = self._items_assignment(settings)
                content_id = self.preview_items_module.prepare(settings, now, assignment)
                item = self.preview_items_module.resolve(settings, content_id)

        panel = self._panel_for_item(settings, item)
        rendered = self._render_panel(panel, settings, display_now)
        if device:
            self._remember_current(rendered)
        return rendered

    def render_current(self) -> RenderedDisplay | None:
        with self._current_display_lock:
            return self._current_display

    def _remember_current(self, rendered: RenderedDisplay) -> None:
        with self._current_display_lock:
            self._current_display = rendered
            try:
                self.current_display_path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    dir=self.current_display_path.parent,
                    prefix=f".{self.current_display_path.name}.",
                    suffix=".png",
                    delete=False,
                ) as handle:
                    temporary_path = Path(handle.name)
                rendered.image.save(temporary_path, format="PNG")
                os.replace(temporary_path, self.current_display_path)
            except OSError:
                if "temporary_path" in locals():
                    temporary_path.unlink(missing_ok=True)

    def _load_current_display(self) -> RenderedDisplay | None:
        try:
            with Image.open(self.current_display_path) as source:
                image = source.convert("1")
            framebuffer = image_to_framebuffer(image)
        except (OSError, ValueError):
            return None
        return RenderedDisplay(item_id=0, image=image, framebuffer=framebuffer)

    def render_next(self, now: datetime | None = None) -> RenderedDisplay:
        settings = self.settings()
        now = now or datetime.now()
        next_at = self._next_check_at(settings, now)
        if self._has_forced_panel(settings):
            panel = self._peek_next_panel(settings, now)
        elif settings.mode == "random":
            panel = self._peek_next_panel(settings, now)
        else:
            item = select_scheduled(settings, next_at.time())
            panel = self._panel_for_item(settings, item, next_at)
        return self._render_panel(panel, settings, next_at)

    def _render_panel(
        self,
        panel: PreparedPanel,
        settings: Settings,
        display_now: datetime,
    ) -> RenderedDisplay:
        image = render_panel(
            panel,
            settings,
            display_now,
            self.device_modules,
            self.status_modules,
        )
        item_id = next(
            (
                slot.content_id
                for slot in panel.slots
                if slot.module == ItemsModule.name and type(slot.content_id) is int
            ),
            0,
        )
        return RenderedDisplay(
            item_id=item_id,
            image=image,
            framebuffer=image_to_framebuffer(image),
        )

    def _panel_for_item(
        self,
        settings: Settings,
        item: Item,
        next_at: datetime | None = None,
    ) -> PreparedPanel:
        at = next_at or datetime.now()
        slots: list[PreparedSlot] = []
        for assignment in settings.panel.slots:
            if assignment.module == ItemsModule.name:
                content_id: int | str = item.id
            else:
                module = self.preview_modules[assignment.module]
                content_id = module.prepare(settings, at, assignment)
            slots.append(PreparedSlot(assignment.slot_id, assignment.module, content_id))
        return PreparedPanel(settings.panel.template, tuple(slots), next_at)

    def change(self, item_id: int, now: datetime | None = None) -> datetime:
        settings = self.settings()
        item_ids = {item.id for item in settings.items}
        if item_id not in item_ids:
            raise ValueError(f"unknown item id: {item_id}")

        now = now or datetime.now()
        next_at = self._next_check_at(settings, now)
        item = next(item for item in settings.items if item.id == item_id)
        with self._next_panel_lock:
            self._next_panel = self._panel_for_item(settings, item, next_at)
            self._next_panel_key = self._panel_key(settings)
            self._next_panel_forced = True
        return next_at

    def select_font(self, group: str, name: str) -> Path:
        with self._config_write_lock:
            settings = self.settings()
            if group == "chinese":
                choices = settings.fonts
                config_key = "font"
            elif group == "latin":
                choices = settings.latin_fonts
                config_key = "latin_font"
            else:
                raise ValueError(f"unknown font group: {group}")
            choice = next((choice for choice in choices if choice.name == name), None)
            if choice is None:
                raise ValueError(f"unknown font: {name}")
            if not choice.path.is_file():
                raise ValueError(f"font file does not exist: {choice.path}")

            try:
                raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
                raw[config_key] = str(choice.path)
                with tempfile.NamedTemporaryFile(
                    "w",
                    encoding="utf-8",
                    dir=self.config_path.parent,
                    prefix=f".{self.config_path.name}.",
                    delete=False,
                ) as handle:
                    yaml.safe_dump(raw, handle, allow_unicode=True, sort_keys=False)
                    temporary_path = Path(handle.name)
                os.replace(temporary_path, self.config_path)
            except OSError as exc:
                raise ConfigError(f"config file cannot be updated: {self.config_path}") from exc
            return choice.path

    def next_check_seconds(self, now: datetime | None = None) -> int:
        settings = self.settings()
        now = now or datetime.now()
        next_check = self._next_check_at(settings, now)
        return max(1, math.ceil((next_check - now).total_seconds()))

    def next_check_at(self, now: datetime | None = None) -> datetime:
        settings = self.settings()
        return self._next_check_at(settings, now or datetime.now())

    @staticmethod
    def _next_check_at(settings: Settings, now: datetime) -> datetime:
        start = datetime.combine(now.date(), settings.active_start)
        end = datetime.combine(now.date(), settings.active_end)

        if now < start:
            next_check = start
        elif now >= end:
            next_check = start + timedelta(days=1)
        else:
            interval = timedelta(minutes=settings.refresh_minutes)
            elapsed = now - start
            completed_intervals = elapsed // interval
            next_check = start + (completed_intervals + 1) * interval
            if next_check >= end:
                next_check = start + timedelta(days=1)

        return next_check

    def _peek_next_panel(self, settings: Settings, now: datetime) -> PreparedPanel:
        with self._next_panel_lock:
            return self._ensure_next_panel_locked(settings, now)

    def _consume_next_panel(self, settings: Settings, now: datetime) -> PreparedPanel:
        with self._next_panel_lock:
            current = self._ensure_next_panel_locked(settings, now)
            next_at = self._next_check_at(settings, now)
            self._next_panel = self._prepare_panel(settings, next_at)
            self._next_panel_key = self._panel_key(settings)
            self._next_panel_forced = False
            return current

    def _ensure_next_panel_locked(
        self,
        settings: Settings,
        now: datetime,
    ) -> PreparedPanel:
        key = self._panel_key(settings)
        if self._next_panel is None or self._next_panel_key != key:
            next_at = self._next_check_at(settings, now)
            self._next_panel = self._prepare_panel(settings, next_at)
            self._next_panel_key = key
            self._next_panel_forced = False
        return self._next_panel

    def _has_forced_panel(self, settings: Settings) -> bool:
        with self._next_panel_lock:
            if self._next_panel_key != self._panel_key(settings):
                self._next_panel = None
                self._next_panel_key = None
                self._next_panel_forced = False
            return self._next_panel_forced

    def _consume_forced_panel(
        self,
        settings: Settings,
        now: datetime,
    ) -> PreparedPanel | None:
        with self._next_panel_lock:
            if self._next_panel_key != self._panel_key(settings):
                self._next_panel = None
                self._next_panel_key = None
                self._next_panel_forced = False
                return None
            if not self._next_panel_forced or self._next_panel is None:
                return None
            panel = self._next_panel
            for prepared in panel.slots:
                if prepared.module == ItemsModule.name and type(prepared.content_id) is int:
                    self.device_items_module.remember(prepared.content_id)
            if settings.mode == "random":
                next_at = self._next_check_at(settings, now)
                self._next_panel = self._prepare_panel(settings, next_at)
                self._next_panel_key = self._panel_key(settings)
            else:
                self._next_panel = None
                self._next_panel_key = None
            self._next_panel_forced = False
            return panel

    def _prepare_panel(self, settings: Settings, at: datetime) -> PreparedPanel:
        slots: list[PreparedSlot] = []
        for assignment in settings.panel.slots:
            module = self.device_modules.get(assignment.module)
            if module is None:
                raise ConfigError(f"unknown module: {assignment.module}")
            content_id = module.prepare(settings, at, assignment)
            slots.append(PreparedSlot(assignment.slot_id, assignment.module, content_id))
        return PreparedPanel(settings.panel.template, tuple(slots), at)

    @staticmethod
    def _items_assignment(settings: Settings):
        for assignment in settings.panel.slots:
            if assignment.module == ItemsModule.name:
                return assignment
        raise ConfigError("selected panel has no items module")

    @staticmethod
    def _panel_key(settings: Settings) -> tuple[object, ...]:
        return (
            settings.panel,
            settings.mode,
            settings.random_items,
            settings.schedule,
            tuple((item.id, item.type, item.text) for item in settings.items),
        )
