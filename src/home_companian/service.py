from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta
import math
from pathlib import Path
import random
from threading import Lock
import os
import tempfile

import yaml

from PIL import Image

from .checklists import ChecklistItem, ChecklistStore
from .config import (
    Config,
    ConfigError,
    DEFAULT_CONFIG_PATH,
    Item,
    RewardConfig,
    Settings,
    load_config,
)
from .display_modes import (
    DETECTIVE_MODE,
    FUN_FACT_MODE,
    TASKBOARD_MODE,
    TREASURE_HUNT_MODE,
    DisplayModeStore,
)
from .domain import PanelConfig, SlotAssignment
from .detective import DetectivePuzzle, DetectiveStore
from .devices import KINDLE_6_167PPI, get_device_profile
from .forge.engine import Forge
from .forge.models import Frame, Presentation, Scene, SceneFragment
from .fun_fact_selection import FunFactSelectionStore
from .modules import (
    ChineseCharactersModule,
    ChineseModule,
    ChecklistModule,
    CreativeModule,
    DetectiveModule,
    FunFactModule,
    HealthModule,
    ImagesModule,
    ItemsModule,
    LanguageModule,
    MathModule,
    Module,
    TreasureHuntModule,
)
from .modules.fun_fact import FunFact, load_fun_facts
from .treasure_hunt import TreasureHunt, TreasureHuntBackground, TreasureHuntStore
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
    prepared: PreparedScene | None = None


@dataclass(frozen=True)
class RewardStatus:
    reward: RewardConfig
    score: int

    @property
    def redeemable(self) -> bool:
        return self.score >= self.reward.cost


@dataclass(frozen=True)
class PreparedScene:
    scene: Scene
    panel: PanelConfig


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
        self.display_mode_store = DisplayModeStore(
            self.current_display_path.parent / f"mode-{self.device_id}.yaml"
        )
        self.fun_fact_selection_store = FunFactSelectionStore(
            self.current_display_path.parent / f"fun-fact-{self.device_id}.yaml"
        )
        self.device_items_module = ItemsModule(RandomSelector())
        self.preview_items_module = ItemsModule(RandomSelector())
        self.device_modules: dict[str, Module] = {
            "items": self.device_items_module,
            "language": LanguageModule(),
            "checklist": ChecklistModule(),
            "chinese": ChineseModule(),
            "chinese_characters": ChineseCharactersModule(),
            "creative": CreativeModule(),
            "detective": DetectiveModule(),
            "fun_fact": FunFactModule(),
            "images": ImagesModule(),
            "health": HealthModule(),
            "math": MathModule(),
            "treasure_hunt": TreasureHuntModule(),
        }
        self.preview_modules: dict[str, Module] = {
            "items": self.preview_items_module,
            "language": LanguageModule(),
            "checklist": ChecklistModule(),
            "chinese": ChineseModule(),
            "chinese_characters": ChineseCharactersModule(),
            "creative": CreativeModule(),
            "detective": DetectiveModule(),
            "fun_fact": FunFactModule(),
            "images": ImagesModule(),
            "health": HealthModule(),
            "math": MathModule(),
            "treasure_hunt": TreasureHuntModule(),
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
        self._next_scene: PreparedScene | None = None
        self._next_scene_key: tuple[object, ...] | None = None
        self._next_scene_forced = False
        self._preview_panel_lock = Lock()
        self._preview_panel_queue: list[int] = []
        self._preview_panel_key: tuple[PanelConfig, ...] | None = None
        self._last_preview_panel: int | None = None
        self._selected_preview_lock = Lock()
        self._selected_previews: OrderedDict[str, RenderedDisplay] = OrderedDict()
        self._current_display_lock = Lock()
        self._current_display = self._load_current_display()
        self._delivery_lock = Lock()
        self._pending_display: RenderedDisplay | None = None
        self._pending_display_key: tuple[object, ...] | None = None
        self._last_ack: tuple[str, str] | None = None

    def config(self) -> Config:
        return load_config(self.config_path)

    def settings(self, device_id: str | None = None) -> Settings:
        config = self.config()
        selected_device = device_id or self.device_id
        settings = config.for_device(selected_device)
        profile = get_device_profile(settings.profile_id)
        for panel in settings.panels:
            template = validate_panel(panel)
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
        if device and self.display_mode(now) == TREASURE_HUNT_MODE:
            rendered = self._render_treasure_hunt(settings, now)
            if remember_device:
                self._remember_current(rendered)
            return rendered
        if device and self.display_mode(now) == FUN_FACT_MODE:
            rendered = self._render_fun_fact(settings, now)
            if remember_device:
                self._remember_current(rendered)
            return rendered
        if device and self.display_mode(now) == DETECTIVE_MODE:
            rendered = self._render_detective(settings, now)
            if remember_device:
                self._remember_current(rendered)
            return rendered
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
            prepared = self._prepare_preview_scene(settings, now)
            return self._render_scene(prepared, settings, display_now)
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
                assignment = self._items_assignment(settings, now)
                content_id = self.preview_items_module.prepare(settings, now, assignment)
                item = self.preview_items_module.resolve(settings, content_id)

        prepared = self._scene_for_item(settings, item)
        rendered = self._render_scene(prepared, settings, display_now)
        if device and remember_device:
            self._remember_current(rendered)
        return rendered

    def render_current(self) -> RenderedDisplay | None:
        with self._current_display_lock:
            return self._current_display

    def continue_current(self, now: datetime | None = None) -> datetime:
        """Use the confirmed current CrowPanel image for the next delivery."""
        now = now or datetime.now()
        settings = self.settings()
        if not settings.profile_id.startswith("crowpanel"):
            raise ValueError("continue current is only supported for CrowPanel")
        with self._current_display_lock:
            if self._current_display is None:
                raise ValueError("device has not confirmed a current display")
            current = self._current_display
            image = current.image.copy()

        next_at = self._next_check_at(settings, now)
        if current.prepared is not None:
            rendered = self._render_scene(current.prepared, settings, next_at)
        else:
            profile = get_device_profile(settings.profile_id)
            scene_id = (
                f"continue-current:{current.frame.id}:{next_at.isoformat()}"
            )
            rendered = RenderedDisplay(
                item_id=current.item_id,
                image=image,
                frame=self.forge.encode(image, scene_id, profile, now),
            )
        with self._delivery_lock:
            self._pending_display = rendered
            self._pending_display_key = self._delivery_key(now)
            self._last_ack = None
        return next_at

    def store_selected_preview(self, rendered: RenderedDisplay) -> str:
        preview_id = rendered.frame.id
        with self._selected_preview_lock:
            self._selected_previews[preview_id] = rendered
            self._selected_previews.move_to_end(preview_id)
            while len(self._selected_previews) > 16:
                self._selected_previews.popitem(last=False)
        return preview_id

    def selected_preview(self, preview_id: str) -> RenderedDisplay:
        with self._selected_preview_lock:
            try:
                rendered = self._selected_previews[preview_id]
            except KeyError as exc:
                raise ValueError(f"unknown preview id: {preview_id}") from exc
            self._selected_previews.move_to_end(preview_id)
            return rendered

    def deliver(self, now: datetime | None = None) -> RenderedDisplay:
        now = now or datetime.now()
        with self._delivery_lock:
            key = self._delivery_key(now)
            if self._pending_display is None or self._pending_display_key != key:
                self._pending_display = self.render(
                    device=True,
                    remember_device=False,
                    now=now,
                )
                self._pending_display_key = key
                self._publish_rendered_image(self._pending_display)
            return self._pending_display

    def refresh_delivery(self, now: datetime | None = None) -> RenderedDisplay:
        """Replace the pending frame so the device's next wake gets fresh state."""
        now = now or datetime.now()
        if self.display_mode(now) == TASKBOARD_MODE:
            self._peek_next_scene(self.settings(), now)
        self.refresh_prepared_checklists(now)
        with self._delivery_lock:
            rendered = self.render(
                device=True,
                remember_device=False,
                now=now,
            )
            self._pending_display = rendered
            self._pending_display_key = self._delivery_key(now)
            self._last_ack = None
            self._publish_rendered_image(rendered)
            return rendered

    def _publish_rendered_image(self, rendered: RenderedDisplay) -> None:
        settings = self.settings()
        if not settings.profile_id.startswith("kindle_"):
            return
        rendered_dir = settings.library_dir / "rendered"
        rendered_dir.mkdir(parents=True, exist_ok=True)
        target = rendered_dir / f"{self.device_id}.png"
        if target.exists():
            with target.open("r+b") as handle:
                handle.write(rendered.frame.payload)
                handle.truncate()
                handle.flush()
                os.fsync(handle.fileno())
            return
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=rendered_dir,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(rendered.frame.payload)
            os.replace(temporary_path, target)
        except OSError:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise

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
                self._pending_display_key = None
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
                image_size = source.size
                configured_profile = get_device_profile(self.settings().profile_id)
                profiles = [configured_profile]
                if configured_profile.id.startswith("kindle_"):
                    profiles.append(KINDLE_6_167PPI)
                profile = next(
                    candidate
                    for candidate in profiles
                    if (candidate.width, candidate.height) == image_size
                )
                image_mode = "L" if profile.grayscale_levels > 2 else "1"
                image = source.convert(image_mode)
            frame = self.forge.encode(image, "restored-current", profile, datetime.now())
        except (OSError, StopIteration, ValueError, ConfigError):
            return None
        return RenderedDisplay(item_id=0, image=image, frame=frame)

    def render_next(self, now: datetime | None = None) -> RenderedDisplay:
        settings = self.settings()
        now = now or datetime.now()
        if self.display_mode(now) == TREASURE_HUNT_MODE:
            return self._render_treasure_hunt(settings, now)
        if self.display_mode(now) == FUN_FACT_MODE:
            return self._render_fun_fact(settings, now)
        if self.display_mode(now) == DETECTIVE_MODE:
            return self._render_detective(settings, now)
        return self._render_taskboard_next(settings, now)

    def _render_taskboard_next(
        self,
        settings: Settings,
        now: datetime,
    ) -> RenderedDisplay:
        next_at = self._next_check_at(settings, now)
        if self._has_forced_scene(settings):
            prepared = self._peek_next_scene(settings, now)
        elif settings.mode == "random":
            prepared = self._peek_next_scene(settings, now)
        else:
            item = select_scheduled(settings, next_at.time())
            prepared = self._scene_for_item(settings, item, next_at)
        return self._render_scene(prepared, settings, next_at)

    def preview_taskboard_delivery(
        self,
        now: datetime | None = None,
    ) -> RenderedDisplay:
        """Preview the taskboard independently of the selected display mode."""
        now = now or datetime.now()
        settings = self.settings()
        if self._has_forced_scene(settings) or settings.mode == "random":
            self._peek_next_scene(settings, now)
            self.refresh_prepared_checklists(now)
            prepared = self._peek_next_scene(settings, now)
        else:
            item = select_scheduled(settings, now.time())
            prepared = self._scene_for_item(settings, item, now)
        return self._render_scene(prepared, settings, now)

    def preview_next_delivery(self, now: datetime | None = None) -> RenderedDisplay:
        """Preview the pending delivery, or the scene the next GET would consume."""
        now = now or datetime.now()
        with self._delivery_lock:
            if (
                self._pending_display is not None
                and self._pending_display_key == self._delivery_key(now)
            ):
                return self._pending_display
            self._pending_display = None
            self._pending_display_key = None
            return self.render_next(now)

    def _render_scene(
        self,
        prepared: PreparedScene,
        settings: Settings,
        display_now: datetime,
    ) -> RenderedDisplay:
        scene = prepared.scene
        profile = get_device_profile(settings.profile_id)
        output = self.forge.render(
            scene,
            Presentation.from_panel(prepared.panel),
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
            prepared=prepared,
        )

    def _render_treasure_hunt(
        self,
        settings: Settings,
        now: datetime,
    ) -> RenderedDisplay:
        panel = PanelConfig(
            "portrait_1",
            (SlotAssignment(1, TreasureHuntModule.name),),
        )
        portrait_settings = replace(
            settings,
            profile_id=KINDLE_6_167PPI.id,
            panels=(panel,),
            display_profiles=(),
        )
        prepared = self._prepare_panel(
            portrait_settings,
            now,
            panel,
            self.device_modules,
        )
        return self._render_scene(prepared, portrait_settings, now)

    def _render_fun_fact(
        self,
        settings: Settings,
        now: datetime,
    ) -> RenderedDisplay:
        fact_name = self.selected_fun_fact()
        panel = PanelConfig(
            "kindle_landscape_1",
            (SlotAssignment(1, FunFactModule.name, (("name", fact_name),)),),
        )
        prepared = self._prepare_panel(
            settings,
            now,
            panel,
            self.device_modules,
        )
        return self._render_scene(prepared, settings, now)

    def _render_detective(
        self,
        settings: Settings,
        now: datetime,
        preview: bool = False,
    ) -> RenderedDisplay:
        panel = PanelConfig(
            "kindle_landscape_1",
            (
                SlotAssignment(
                    1,
                    DetectiveModule.name,
                    (("preview", "true"),) if preview else (),
                ),
            ),
        )
        prepared = self._prepare_panel(
            settings,
            now,
            panel,
            self.device_modules,
        )
        return self._render_scene(prepared, settings, now)

    def _delivery_key(self, now: datetime) -> tuple[object, ...]:
        return (now.date(), self.display_mode(now))

    def _scene_for_item(
        self,
        settings: Settings,
        item: Item,
        next_at: datetime | None = None,
    ) -> PreparedScene:
        at = next_at or datetime.now()
        panel = self._items_panel(settings, at)
        fragments: list[SceneFragment] = []
        for index, assignment in enumerate(panel.slots):
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
        return PreparedScene(Scene.create(tuple(fragments), next_at), panel)

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
        with self._delivery_lock:
            self._pending_display = None
            self._pending_display_key = None
            self._last_ack = None
        return next_at

    def change_preview(
        self,
        preview_id: str,
        now: datetime | None = None,
    ) -> datetime:
        rendered = self.selected_preview(preview_id)
        if rendered.prepared is None:
            raise ValueError("selected preview cannot be scheduled")
        now = now or datetime.now()
        settings = self.settings()
        next_at = self._next_check_at(settings, now)
        with self._next_scene_lock:
            self._next_scene = rendered.prepared
            self._next_scene_key = self._scene_key(settings)
            self._next_scene_forced = True
        with self._delivery_lock:
            self._pending_display = None
            self._pending_display_key = None
            self._last_ack = None
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

    def checklist_items(
        self,
        now: datetime | None = None,
    ) -> tuple[tuple[str, ChecklistItem, bool], ...]:
        now = now or datetime.now()
        settings = self.settings()
        store = ChecklistStore(settings.library_dir)
        completed_ids = store.completed_ids(now.date())
        items_by_id = {item.id: item for item in store.items()}
        rows: list[tuple[str, ChecklistItem, bool]] = []
        for group in settings.checklist_groups:
            for item_id in group.item_ids_for(now.date()):
                try:
                    item = items_by_id[item_id]
                except KeyError as exc:
                    raise ConfigError(
                        f"checklist group {group.id} references unknown item: {item_id}"
                    ) from exc
                rows.append((group.id, item, item.id in completed_ids))
        return tuple(rows)

    def set_checklist_completed(
        self,
        item_id: int,
        completed: bool,
        now: datetime | None = None,
    ) -> None:
        ChecklistStore(self.settings().library_dir).set_completed(
            item_id,
            completed,
            now,
        )

    def reward_status(self, now: datetime | None = None) -> RewardStatus:
        settings = self.settings()
        score = ChecklistStore(settings.library_dir).reward_score(
            settings.reward,
            now,
        )
        return RewardStatus(settings.reward, score)

    def redeem_reward(
        self,
        reward_id: str,
        now: datetime | None = None,
    ) -> RewardStatus:
        settings = self.settings()
        if reward_id != settings.reward.id:
            raise ValueError(f"unknown reward: {reward_id}")
        ChecklistStore(settings.library_dir).redeem(settings.reward, now)
        return self.reward_status(now)

    def treasure_hunt(self) -> TreasureHunt:
        return TreasureHuntStore(self.settings().library_dir).load()

    def treasure_hunt_backgrounds(self) -> tuple[TreasureHuntBackground, ...]:
        return TreasureHuntStore(self.settings().library_dir).backgrounds()

    def treasure_hunt_background_path(self, name: str) -> Path:
        return TreasureHuntStore(self.settings().library_dir).background_path(name)

    def treasure_hunt_check_path(self) -> Path:
        return TreasureHuntStore(self.settings().library_dir).check_path()

    def save_treasure_hunt(
        self,
        background: object,
        texts: object,
        completed: object,
    ) -> TreasureHunt:
        return TreasureHuntStore(self.settings().library_dir).save(
            background,
            texts,
            completed,
        )

    def render_treasure_hunt_preview(
        self,
        now: datetime | None = None,
    ) -> RenderedDisplay:
        settings = self.settings()
        if not settings.profile_id.startswith("kindle_"):
            raise ValueError("treasure hunt preview requires a Kindle device")
        return self._render_treasure_hunt(settings, now or datetime.now())

    def render_fun_fact_preview(
        self,
        now: datetime | None = None,
    ) -> RenderedDisplay:
        settings = self.settings()
        if not settings.profile_id.startswith("kindle_"):
            raise ValueError("fun fact preview requires a Kindle device")
        return self._render_fun_fact(settings, now or datetime.now())

    def detective(self) -> DetectivePuzzle:
        return DetectiveStore(self.settings().library_dir).load()

    def save_detective(
        self,
        title: object,
        mystery: object,
        answer: object,
        hints: object,
        visible: object = None,
    ) -> DetectivePuzzle:
        return DetectiveStore(self.settings().library_dir).save(
            title,
            mystery,
            answer,
            hints,
            visible,
        )

    def render_detective_preview(
        self,
        now: datetime | None = None,
    ) -> RenderedDisplay:
        settings = self.settings()
        if not settings.profile_id.startswith("kindle_"):
            raise ValueError("detective preview requires a Kindle device")
        return self._render_detective(
            settings,
            now or datetime.now(),
            preview=True,
        )

    def fun_facts(self) -> tuple[FunFact, ...]:
        return load_fun_facts(self.settings().library_dir)

    def selected_fun_fact(self) -> str:
        facts = self.fun_facts()
        selected = self.fun_fact_selection_store.selected()
        if selected is not None and any(fact.name == selected for fact in facts):
            return selected
        return facts[0].name

    def select_fun_fact(
        self,
        name: str,
        now: datetime | None = None,
    ) -> RenderedDisplay:
        if not any(fact.name == name for fact in self.fun_facts()):
            raise ValueError(f"unknown fun fact: {name}")
        self.fun_fact_selection_store.select(name)
        now = now or datetime.now()
        if self.display_mode(now) == FUN_FACT_MODE:
            return self.refresh_delivery(now)
        return self.render_fun_fact_preview(now)

    def display_mode(self, now: datetime | None = None) -> str:
        settings = self.settings()
        if not settings.profile_id.startswith("kindle_"):
            return TASKBOARD_MODE
        return self.display_mode_store.selected((now or datetime.now()).date())

    def select_display_mode(
        self,
        mode: str,
        now: datetime | None = None,
    ) -> RenderedDisplay:
        now = now or datetime.now()
        settings = self.settings()
        if not settings.profile_id.startswith("kindle_"):
            raise ValueError("display modes are only supported for Kindle")
        self.display_mode_store.select(mode, now.date())
        with self._delivery_lock:
            rendered = self.render(
                device=True,
                remember_device=False,
                now=now,
            )
            self._pending_display = rendered
            self._pending_display_key = self._delivery_key(now)
            self._last_ack = None
            self._publish_rendered_image(rendered)
            return rendered

    def refresh_prepared_checklists(self, now: datetime | None = None) -> None:
        self._refresh_prepared_modules(
            frozenset({ChecklistModule.name}),
            now,
        )

    def refresh_prepared_treasure_hunts(self) -> None:
        now = datetime.now()
        if self.display_mode(now) != TREASURE_HUNT_MODE:
            return
        with self._delivery_lock:
            self._pending_display = self._render_treasure_hunt(self.settings(), now)
            self._pending_display_key = self._delivery_key(now)
            self._last_ack = None
            self._publish_rendered_image(self._pending_display)

    def refresh_prepared_detectives(self) -> None:
        now = datetime.now()
        if self.display_mode(now) != DETECTIVE_MODE:
            return
        with self._delivery_lock:
            self._pending_display = self._render_detective(self.settings(), now)
            self._pending_display_key = self._delivery_key(now)
            self._last_ack = None
            self._publish_rendered_image(self._pending_display)

    def _refresh_prepared_modules(
        self,
        module_names: frozenset[str],
        at: datetime | None = None,
    ) -> None:
        settings = self.settings()
        with self._next_scene_lock:
            if (
                self._next_scene is None
                or self._next_scene_key != self._scene_key(settings)
            ):
                return
            explicit_at = at
            at = at or self._next_scene.scene.target_at or datetime.now()
            fragments = list(self._next_scene.scene.fragments)
            for index, assignment in enumerate(self._next_scene.panel.slots):
                if assignment.module not in module_names:
                    continue
                fragments[index] = SceneFragment(
                    fragments[index].id,
                    assignment.module,
                    self.device_modules[assignment.module].prepare(
                        settings, at, assignment
                    ),
                    assignment.module,
                )
            self._next_scene = PreparedScene(
                Scene.create(
                    tuple(fragments),
                    explicit_at or self._next_scene.scene.target_at,
                ),
                self._next_scene.panel,
            )

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
        if settings.refresh_periods:
            for period in settings.refresh_periods:
                start = datetime.combine(now.date(), period.start)
                end = datetime.combine(now.date(), period.end)
                if now < start:
                    return start
                if now < end:
                    interval = timedelta(minutes=period.minutes)
                    elapsed = now - start
                    return start + (elapsed // interval + 1) * interval
            return datetime.combine(
                now.date() + timedelta(days=1),
                settings.refresh_periods[0].start,
            )

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

    def _peek_next_scene(self, settings: Settings, now: datetime) -> PreparedScene:
        with self._next_scene_lock:
            return self._ensure_next_scene_locked(settings, now)

    def _consume_next_scene(self, settings: Settings, now: datetime) -> PreparedScene:
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
    ) -> PreparedScene:
        key = self._scene_key(settings)
        target_at = (
            self._next_scene.scene.target_at
            if self._next_scene is not None
            else None
        )
        if (
            self._next_scene is None
            or self._next_scene_key != key
            or (target_at is not None and target_at.date() < now.date())
        ):
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
    ) -> PreparedScene | None:
        with self._next_scene_lock:
            if self._next_scene_key != self._scene_key(settings):
                self._next_scene = None
                self._next_scene_key = None
                self._next_scene_forced = False
                return None
            if not self._next_scene_forced or self._next_scene is None:
                return None
            scene = self._next_scene
            for fragment in scene.scene.fragments:
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

    def _prepare_scene(self, settings: Settings, at: datetime) -> PreparedScene:
        panels = settings.panels_at(at)
        frequencies = settings.panel_frequencies_at(at)
        panel = (
            random.choices(panels, weights=frequencies, k=1)[0]
            if frequencies
            else random.choice(panels)
        )
        return self._prepare_panel(settings, at, panel, self.device_modules)

    def _prepare_preview_scene(
        self,
        settings: Settings,
        at: datetime,
    ) -> PreparedScene:
        available_panels = settings.panels_at(at)
        with self._preview_panel_lock:
            key = available_panels
            if self._preview_panel_key != key:
                self._preview_panel_queue = []
                self._preview_panel_key = key
                self._last_preview_panel = None
            if not self._preview_panel_queue:
                self._preview_panel_queue = list(range(len(available_panels)))
                random.shuffle(self._preview_panel_queue)
                if (
                    len(self._preview_panel_queue) > 1
                    and self._preview_panel_queue[0] == self._last_preview_panel
                ):
                    self._preview_panel_queue[0], self._preview_panel_queue[1] = (
                        self._preview_panel_queue[1],
                        self._preview_panel_queue[0],
                    )
            panel_index = self._preview_panel_queue.pop(0)
            self._last_preview_panel = panel_index
        return self._prepare_panel(
            settings,
            at,
            available_panels[panel_index],
            self.preview_modules,
        )

    @staticmethod
    def _prepare_panel(
        settings: Settings,
        at: datetime,
        panel: PanelConfig,
        modules: dict[str, Module],
    ) -> PreparedScene:
        fragments: list[SceneFragment] = []
        for index, assignment in enumerate(panel.slots):
            module = modules.get(assignment.module)
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
        return PreparedScene(Scene.create(tuple(fragments), at), panel)

    @staticmethod
    def _items_assignment(settings: Settings, at: datetime):
        for assignment in DisplayService._items_panel(settings, at).slots:
            if assignment.module == ItemsModule.name:
                return assignment
        raise ConfigError("selected panel has no items module")

    @staticmethod
    def _items_panel(settings: Settings, at: datetime) -> PanelConfig:
        for panel in settings.panels_at(at):
            if any(slot.module == ItemsModule.name for slot in panel.slots):
                return panel
        raise ConfigError("selected presentation has no items module")

    @staticmethod
    def _scene_key(settings: Settings) -> tuple[object, ...]:
        return (
            settings.device_id,
            settings.channel_id,
            settings.profile_id,
            settings.refresh_minutes,
            settings.active_start,
            settings.active_end,
            settings.refresh_periods,
            settings.display_profiles,
            settings.panels,
            settings.mode,
            settings.random_items,
            settings.schedule,
            tuple((item.id, item.type, item.text) for item in settings.items),
        )
