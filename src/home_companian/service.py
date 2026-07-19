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

from .config import Config, ConfigError, DEFAULT_CONFIG_PATH, Item, Settings, load_config
from .devices import get_device_profile
from .forge.engine import Forge
from .forge.models import Frame, Presentation, Scene, SceneFragment
from .modules import (
    ChineseModule,
    HealthModule,
    ImagesModule,
    ItemsModule,
    MathModule,
    Module,
)
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
    frame: Frame


class DisplayService:
    def __init__(
        self,
        config_path: Path = DEFAULT_CONFIG_PATH,
        current_display_path: Path | None = None,
        device_id: str | None = None,
    ) -> None:
        self.config_path = config_path
        self.device_id = device_id or load_config(config_path).default_device
        if current_display_path is None:
            filename = (
                "current.png"
                if self.device_id == "wall_panel"
                else f"current-{self.device_id}.png"
            )
            current_display_path = Path(
                f"~/.local/state/home_companian/{filename}"
            ).expanduser()
        self.current_display_path = current_display_path
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
        self.forge = Forge()
        self._config_write_lock = Lock()
        self._next_scene_lock = Lock()
        self._next_scene: Scene | None = None
        self._next_scene_key: tuple[object, ...] | None = None
        self._next_scene_forced = False
        self._current_display_lock = Lock()
        self._current_display = self._load_current_display()
        self._delivery_lock = Lock()
        self._pending_display: RenderedDisplay | None = None
        self._last_ack: tuple[str, str] | None = None

    def config(self) -> Config:
        return load_config(self.config_path)

    def settings(self, device_id: str | None = None) -> Settings:
        config = self.config()
        selected_device = device_id or self.device_id
        settings = config.for_device(selected_device)
        profile = get_device_profile(settings.profile_id)
        template = validate_panel(settings.panel)
        if (template.width, template.height) != (
            profile.width,
            profile.content_height,
        ):
            raise ConfigError(
                f"selected template must be {profile.width}x{profile.content_height} "
                f"for profile {profile.id}"
            )
        return settings

    def render(
        self,
        preview_time: time | None = None,
        preview_random: bool = False,
        preview_item_id: int | None = None,
        device: bool = False,
        remember_device: bool = True,
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
                forced_scene = self._consume_forced_scene(settings, now)
                if forced_scene is not None:
                    rendered = self._render_scene(forced_scene, settings, display_now)
                    if remember_device:
                        self._remember_current(rendered)
                    return rendered
            if settings.mode == "scheduled":
                item = select_scheduled(settings, now.time())
            elif device:
                scene = self._consume_next_scene(settings, now)
                rendered = self._render_scene(scene, settings, display_now)
                if remember_device:
                    self._remember_current(rendered)
                return rendered
            else:
                assignment = self._items_assignment(settings)
                content_id = self.preview_items_module.prepare(settings, now, assignment)
                item = self.preview_items_module.resolve(settings, content_id)

        scene = self._scene_for_item(settings, item)
        rendered = self._render_scene(scene, settings, display_now)
        if device and remember_device:
            self._remember_current(rendered)
        return rendered

    def render_current(self) -> RenderedDisplay | None:
        with self._current_display_lock:
            return self._current_display

    def deliver(self, now: datetime | None = None) -> RenderedDisplay:
        with self._delivery_lock:
            if self._pending_display is None:
                self._pending_display = self.render(
                    device=True,
                    remember_device=False,
                    now=now,
                )
            return self._pending_display

    def acknowledge(self, frame_id: str, status: str) -> None:
        if status not in {"displayed", "failed"}:
            raise ValueError("ack status must be displayed or failed")
        with self._delivery_lock:
            if self._last_ack == (frame_id, status):
                return
            if self._pending_display is None or self._pending_display.frame.id != frame_id:
                raise ValueError(f"unknown pending frame: {frame_id}")
            if status == "displayed":
                self._remember_current(self._pending_display)
                self._pending_display = None
            self._last_ack = (frame_id, status)

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
            profile = get_device_profile(self.settings().profile_id)
            frame = self.forge.encode(image, "restored-current", profile, datetime.now())
        except (OSError, ValueError, ConfigError):
            return None
        return RenderedDisplay(item_id=0, image=image, frame=frame)

    def render_next(self, now: datetime | None = None) -> RenderedDisplay:
        settings = self.settings()
        now = now or datetime.now()
        next_at = self._next_check_at(settings, now)
        if self._has_forced_scene(settings):
            scene = self._peek_next_scene(settings, now)
        elif settings.mode == "random":
            scene = self._peek_next_scene(settings, now)
        else:
            item = select_scheduled(settings, next_at.time())
            scene = self._scene_for_item(settings, item, next_at)
        return self._render_scene(scene, settings, next_at)

    def preview_next_delivery(self, now: datetime | None = None) -> RenderedDisplay:
        """Preview the pending delivery, or the scene the next GET would consume."""
        with self._delivery_lock:
            if self._pending_display is not None:
                return self._pending_display
            return self.render_next(now)

    def _render_scene(
        self,
        scene: Scene,
        settings: Settings,
        display_now: datetime,
    ) -> RenderedDisplay:
        profile = get_device_profile(settings.profile_id)
        output = self.forge.render(
            scene,
            Presentation.from_panel(settings.panel),
            profile,
            settings,
            display_now,
            self.device_modules,
            self.status_modules,
        )
        item_id = next(
            (
                fragment.content_id
                for fragment in scene.fragments
                if fragment.module == ItemsModule.name
                and type(fragment.content_id) is int
            ),
            0,
        )
        return RenderedDisplay(
            item_id=item_id,
            image=output.image,
            frame=output.frame,
        )

    def _scene_for_item(
        self,
        settings: Settings,
        item: Item,
        next_at: datetime | None = None,
    ) -> Scene:
        at = next_at or datetime.now()
        fragments: list[SceneFragment] = []
        for index, assignment in enumerate(settings.panel.slots):
            if assignment.module == ItemsModule.name:
                content_id: int | str = item.id
            else:
                module = self.preview_modules[assignment.module]
                content_id = module.prepare(settings, at, assignment)
            fragments.append(
                SceneFragment(
                    f"fragment-{index}",
                    assignment.module,
                    content_id,
                    assignment.module,
                )
            )
        return Scene.create(tuple(fragments), next_at)

    def change(self, item_id: int, now: datetime | None = None) -> datetime:
        settings = self.settings()
        item_ids = {item.id for item in settings.items}
        if item_id not in item_ids:
            raise ValueError(f"unknown item id: {item_id}")

        now = now or datetime.now()
        next_at = self._next_check_at(settings, now)
        item = next(item for item in settings.items if item.id == item_id)
        with self._next_scene_lock:
            self._next_scene = self._scene_for_item(settings, item, next_at)
            self._next_scene_key = self._scene_key(settings)
            self._next_scene_forced = True
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

    def _peek_next_scene(self, settings: Settings, now: datetime) -> Scene:
        with self._next_scene_lock:
            return self._ensure_next_scene_locked(settings, now)

    def _consume_next_scene(self, settings: Settings, now: datetime) -> Scene:
        with self._next_scene_lock:
            current = self._ensure_next_scene_locked(settings, now)
            next_at = self._next_check_at(settings, now)
            self._next_scene = self._prepare_scene(settings, next_at)
            self._next_scene_key = self._scene_key(settings)
            self._next_scene_forced = False
            return current

    def _ensure_next_scene_locked(
        self,
        settings: Settings,
        now: datetime,
    ) -> Scene:
        key = self._scene_key(settings)
        if self._next_scene is None or self._next_scene_key != key:
            next_at = self._next_check_at(settings, now)
            self._next_scene = self._prepare_scene(settings, next_at)
            self._next_scene_key = key
            self._next_scene_forced = False
        return self._next_scene

    def _has_forced_scene(self, settings: Settings) -> bool:
        with self._next_scene_lock:
            if self._next_scene_key != self._scene_key(settings):
                self._next_scene = None
                self._next_scene_key = None
                self._next_scene_forced = False
            return self._next_scene_forced

    def _consume_forced_scene(
        self,
        settings: Settings,
        now: datetime,
    ) -> Scene | None:
        with self._next_scene_lock:
            if self._next_scene_key != self._scene_key(settings):
                self._next_scene = None
                self._next_scene_key = None
                self._next_scene_forced = False
                return None
            if not self._next_scene_forced or self._next_scene is None:
                return None
            scene = self._next_scene
            for fragment in scene.fragments:
                if (
                    fragment.module == ItemsModule.name
                    and type(fragment.content_id) is int
                ):
                    self.device_items_module.remember(fragment.content_id)
            if settings.mode == "random":
                next_at = self._next_check_at(settings, now)
                self._next_scene = self._prepare_scene(settings, next_at)
                self._next_scene_key = self._scene_key(settings)
            else:
                self._next_scene = None
                self._next_scene_key = None
            self._next_scene_forced = False
            return scene

    def _prepare_scene(self, settings: Settings, at: datetime) -> Scene:
        fragments: list[SceneFragment] = []
        for index, assignment in enumerate(settings.panel.slots):
            module = self.device_modules.get(assignment.module)
            if module is None:
                raise ConfigError(f"unknown module: {assignment.module}")
            content_id = module.prepare(settings, at, assignment)
            fragments.append(
                SceneFragment(
                    f"fragment-{index}",
                    assignment.module,
                    content_id,
                    assignment.module,
                )
            )
        return Scene.create(tuple(fragments), at)

    @staticmethod
    def _items_assignment(settings: Settings):
        for assignment in settings.panel.slots:
            if assignment.module == ItemsModule.name:
                return assignment
        raise ConfigError("selected panel has no items module")

    @staticmethod
    def _scene_key(settings: Settings) -> tuple[object, ...]:
        return (
            settings.device_id,
            settings.channel_id,
            settings.profile_id,
            settings.panel,
            settings.mode,
            settings.random_items,
            settings.schedule,
            tuple((item.id, item.type, item.text) for item in settings.items),
        )
