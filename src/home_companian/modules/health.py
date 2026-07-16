from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import random
from threading import Lock

from PIL import Image, ImageDraw, ImageFont

from ..config import ConfigError, Settings
from ..domain import Rect, SlotAssignment
from ..image_processing import process_image


@dataclass(frozen=True)
class Exercise:
    id: int
    name: str
    dose: str
    instruction: str


def load_exercises(library_dir: Path) -> tuple[Exercise, ...]:
    path = library_dir / "health" / "exercises.csv"
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"id", "name", "dose", "instruction"}
            if reader.fieldnames is None or set(reader.fieldnames) != required:
                raise ConfigError(
                    "health/exercises.csv must use id,name,dose,instruction"
                )
            exercises: list[Exercise] = []
            seen: set[int] = set()
            for line_number, row in enumerate(reader, 2):
                try:
                    exercise_id = int(row["id"])
                except (TypeError, ValueError) as exc:
                    raise ConfigError(
                        f"health/exercises.csv line {line_number} has invalid id"
                    ) from exc
                if exercise_id <= 0 or exercise_id in seen:
                    raise ConfigError(
                        f"health/exercises.csv line {line_number} has invalid id"
                    )
                values = [row[key].strip() for key in required - {"id"}]
                if any(not value for value in values):
                    raise ConfigError(
                        f"health/exercises.csv line {line_number} has empty text"
                    )
                seen.add(exercise_id)
                exercises.append(
                    Exercise(
                        exercise_id,
                        row["name"].strip(),
                        row["dose"].strip(),
                        row["instruction"].strip(),
                    )
                )
    except OSError as exc:
        raise ConfigError(f"health exercise file cannot be opened: {path}") from exc
    if not exercises:
        raise ConfigError("health/exercises.csv must contain at least one exercise")
    return tuple(exercises)


class HealthModule:
    name = "health"

    def __init__(self) -> None:
        self._last_id: int | None = None
        self._lock = Lock()

    def prepare(
        self,
        settings: Settings,
        at: datetime,
        assignment: SlotAssignment,
    ) -> int:
        del at, assignment
        exercises = load_exercises(settings.library_dir)
        with self._lock:
            candidates = tuple(
                exercise
                for exercise in exercises
                if len(exercises) == 1 or exercise.id != self._last_id
            )
            selected = random.choice(candidates)
            self._last_id = selected.id
            return selected.id

    def render(
        self,
        settings: Settings,
        content_id: int | str,
        rect: Rect,
        now: datetime,
    ) -> Image.Image:
        del now
        if type(content_id) is not int:
            raise ConfigError(f"invalid health content id: {content_id}")
        exercise = next(
            (item for item in load_exercises(settings.library_dir) if item.id == content_id),
            None,
        )
        if exercise is None:
            raise ConfigError(f"unknown health exercise id: {content_id}")
        frames = tuple(
            self._load_frame(settings.library_dir, exercise.id, number)
            for number in (1, 2)
        )
        if rect.width >= 500:
            image = self._render_wide(settings, exercise, frames, rect)
        else:
            image = self._render_compact(settings, exercise, frames, rect)
        return image.point(lambda pixel: 255 if pixel > 180 else 0, mode="1")

    @staticmethod
    def _load_frame(library_dir: Path, exercise_id: int, number: int) -> Image.Image:
        path = library_dir / "health" / "images" / str(exercise_id) / f"{number}.png"
        try:
            with Image.open(path) as source:
                if source.format != "PNG":
                    raise ConfigError(f"health image must be PNG: {path}")
                return source.convert("L")
        except OSError as exc:
            raise ConfigError(f"health image cannot be opened: {path}") from exc

    @staticmethod
    def _frame(source: Image.Image, size: tuple[int, int]) -> Image.Image:
        return process_image(
            source,
            size=size,
            fit="contain",
            binarize="threshold",
        ).convert("L")

    def _render_wide(
        self,
        settings: Settings,
        exercise: Exercise,
        frames: tuple[Image.Image, Image.Image],
        rect: Rect,
    ) -> Image.Image:
        image = Image.new("L", (rect.width, rect.height), 255)
        draw = ImageDraw.Draw(image)
        text_width = min(260, rect.width // 3)
        name_font = ImageFont.truetype(str(settings.font), 44)
        detail_font = ImageFont.truetype(str(settings.font), 30)
        draw.text((18, 14), exercise.name, font=name_font, fill=0)
        draw.text((18, 76), exercise.dose, font=detail_font, fill=0)

        available = rect.width - text_width - 42
        frame_width = max(1, (available - 26) // 2)
        frame_size = (frame_width, rect.height - 20)
        first = self._frame(frames[0], frame_size)
        second = self._frame(frames[1], frame_size)
        first_x = text_width
        second_x = text_width + frame_width + 26
        image.paste(first, (first_x, 10))
        image.paste(second, (second_x, 10))
        arrow_font = ImageFont.truetype(str(settings.font), 28)
        draw.text((text_width + frame_width + 2, rect.height // 2 - 18), "→", font=arrow_font, fill=0)
        return image

    def _render_compact(
        self,
        settings: Settings,
        exercise: Exercise,
        frames: tuple[Image.Image, Image.Image],
        rect: Rect,
    ) -> Image.Image:
        image = Image.new("L", (rect.width, rect.height), 255)
        draw = ImageDraw.Draw(image)
        name_font = ImageFont.truetype(str(settings.font), 28)
        dose_font = ImageFont.truetype(str(settings.font), 22)
        draw.text((8, 2), exercise.name, font=name_font, fill=0)
        draw.text((8, 36), exercise.dose, font=dose_font, fill=0)
        gap = 10
        frame_width = max(1, (rect.width - gap) // 2)
        frame_size = (frame_width, max(1, rect.height - 66))
        image.paste(self._frame(frames[0], frame_size), (0, 64))
        image.paste(self._frame(frames[1], frame_size), (frame_width + gap, 64))
        return image
