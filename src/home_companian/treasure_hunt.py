from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tempfile
from threading import Lock
from typing import Any

import yaml

from .config import ConfigError


TEXT_BOX_COUNT = 6
MAX_TEXT_LENGTH = 200
_STORE_LOCK = Lock()


@dataclass(frozen=True)
class TreasureHuntBackground:
    name: str
    boxes: tuple[tuple[float, float, float, float], ...]


@dataclass(frozen=True)
class TreasureHunt:
    background: TreasureHuntBackground
    texts: tuple[str, ...]
    completed: tuple[bool, ...]


class TreasureHuntStore:
    def __init__(self, library_dir: Path) -> None:
        self.root = library_dir / "treasure_hunt"
        self.background_dir = self.root / "background"
        self.current_path = self.root / "current.yaml"

    def backgrounds(self) -> tuple[TreasureHuntBackground, ...]:
        try:
            paths = sorted(
                path
                for path in self.background_dir.iterdir()
                if path.is_file() and path.suffix.lower() == ".png"
            )
        except OSError as exc:
            raise ConfigError(
                f"treasure hunt backgrounds cannot be opened: {self.background_dir}"
            ) from exc
        if not paths:
            raise ConfigError("treasure hunt must contain at least one PNG background")
        return tuple(self._load_background(path.name) for path in paths)

    def load(self) -> TreasureHunt:
        backgrounds = self.backgrounds()
        if not self.current_path.exists():
            return TreasureHunt(
                backgrounds[0],
                ("",) * TEXT_BOX_COUNT,
                (False,) * TEXT_BOX_COUNT,
            )
        try:
            raw = yaml.safe_load(self.current_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigError(
                f"treasure hunt state cannot be opened: {self.current_path}"
            ) from exc
        if not isinstance(raw, dict):
            raise ConfigError("treasure_hunt/current.yaml must be a mapping")
        background_name = raw.get("background")
        texts = raw.get("texts")
        completed = raw.get("completed", [False] * TEXT_BOX_COUNT)
        return TreasureHunt(
            self._background_by_name(backgrounds, background_name),
            self._validate_texts(texts),
            self._validate_completed(completed),
        )

    def save(
        self,
        background_name: object,
        texts: object,
        completed: object,
    ) -> TreasureHunt:
        backgrounds = self.backgrounds()
        hunt = TreasureHunt(
            self._background_by_name(backgrounds, background_name),
            self._validate_texts(texts),
            self._validate_completed(completed),
        )
        payload = {
            "background": hunt.background.name,
            "texts": list(hunt.texts),
            "completed": list(hunt.completed),
        }
        with _STORE_LOCK:
            try:
                self.root.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    "w",
                    encoding="utf-8",
                    dir=self.root,
                    prefix=".current.",
                    suffix=".yaml",
                    delete=False,
                ) as handle:
                    temporary_path = Path(handle.name)
                    yaml.safe_dump(
                        payload,
                        handle,
                        allow_unicode=True,
                        sort_keys=False,
                    )
                os.replace(temporary_path, self.current_path)
            except OSError as exc:
                if "temporary_path" in locals():
                    temporary_path.unlink(missing_ok=True)
                raise ConfigError(
                    f"treasure hunt state cannot be updated: {self.current_path}"
                ) from exc
        return hunt

    def background_path(self, name: str) -> Path:
        background = self._background_by_name(self.backgrounds(), name)
        return self.background_dir / background.name

    def check_path(self) -> Path:
        path = self.root / "check_grey.png"
        if not path.is_file():
            raise ConfigError(f"treasure hunt check image does not exist: {path}")
        return path

    def _load_background(self, name: str) -> TreasureHuntBackground:
        image_path = self.background_dir / name
        layout_path = image_path.with_suffix(".yaml")
        try:
            raw = yaml.safe_load(layout_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigError(
                f"treasure hunt layout cannot be opened: {layout_path}"
            ) from exc
        if not isinstance(raw, dict) or set(raw) != {"text_boxes"}:
            raise ConfigError(f"{layout_path} must contain only text_boxes")
        raw_boxes = raw["text_boxes"]
        if not isinstance(raw_boxes, list) or len(raw_boxes) != TEXT_BOX_COUNT:
            raise ConfigError(
                f"{layout_path}.text_boxes must contain exactly {TEXT_BOX_COUNT} boxes"
            )
        boxes: list[tuple[float, float, float, float]] = []
        for index, raw_box in enumerate(raw_boxes, 1):
            if (
                not isinstance(raw_box, list)
                or len(raw_box) != 4
                or not all(type(value) in {int, float} for value in raw_box)
            ):
                raise ConfigError(
                    f"{layout_path}.text_boxes[{index}] must be [x, y, width, height]"
                )
            x, y, width, height = (float(value) for value in raw_box)
            if (
                x < 0
                or y < 0
                or width <= 0
                or height <= 0
                or x + width > 1
                or y + height > 1
            ):
                raise ConfigError(
                    f"{layout_path}.text_boxes[{index}] must stay within 0..1"
                )
            boxes.append((x, y, width, height))
        return TreasureHuntBackground(name, tuple(boxes))

    @staticmethod
    def _background_by_name(
        backgrounds: tuple[TreasureHuntBackground, ...],
        name: object,
    ) -> TreasureHuntBackground:
        if not isinstance(name, str) or Path(name).name != name:
            raise ValueError("treasure hunt background must be selected")
        background = next(
            (candidate for candidate in backgrounds if candidate.name == name),
            None,
        )
        if background is None:
            raise ValueError(f"unknown treasure hunt background: {name}")
        return background

    @staticmethod
    def _validate_texts(value: Any) -> tuple[str, ...]:
        if not isinstance(value, list) or len(value) != TEXT_BOX_COUNT:
            raise ValueError(
                f"treasure hunt texts must contain exactly {TEXT_BOX_COUNT} entries"
            )
        if not all(isinstance(text, str) for text in value):
            raise ValueError("treasure hunt texts must be text")
        texts = tuple(text.strip() for text in value)
        if any(len(text) > MAX_TEXT_LENGTH for text in texts):
            raise ValueError(
                f"each treasure hunt text must be at most {MAX_TEXT_LENGTH} characters"
            )
        return texts

    @staticmethod
    def _validate_completed(value: Any) -> tuple[bool, ...]:
        if (
            not isinstance(value, list)
            or len(value) != TEXT_BOX_COUNT
            or not all(type(completed) is bool for completed in value)
        ):
            raise ValueError(
                f"treasure hunt completed must contain exactly {TEXT_BOX_COUNT} booleans"
            )
        return tuple(value)
