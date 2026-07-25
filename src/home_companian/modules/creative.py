from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import random
import re
from threading import Lock

from PIL import Image, ImageDraw, ImageFont

from ..config import ConfigError, Settings
from ..domain import Rect, SlotAssignment
from .chinese import _is_han


ENGLISH_WORD = re.compile(r"^[a-z]+$")
LANGUAGES = {"chinese", "english"}


def load_creative_prompts(library_dir: Path, language: str) -> tuple[str, ...]:
    if language not in LANGUAGES:
        raise ConfigError("creative module language must be chinese or english")
    path = library_dir / "creative" / f"{language}.txt"
    try:
        values = tuple(
            line.strip().lower() if language == "english" else line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    except OSError as exc:
        raise ConfigError(f"creative prompt file cannot be opened: {path}") from exc
    if len(values) < 4 or len(set(values)) != len(values):
        raise ConfigError(f"{path} must contain at least four unique entries")
    if language == "chinese" and any(
        len(value) != 1 or not _is_han(value) for value in values
    ):
        raise ConfigError(f"{path} must contain one Chinese character per line")
    if language == "english" and any(
        ENGLISH_WORD.fullmatch(value) is None for value in values
    ):
        raise ConfigError(f"{path} must contain one lowercase English word per line")
    return values


class CreativeModule:
    name = "creative"

    def __init__(self) -> None:
        self._last: dict[str, tuple[str, ...]] = {}
        self._lock = Lock()

    def prepare(
        self,
        settings: Settings,
        at: datetime,
        assignment: SlotAssignment,
    ) -> str:
        del at
        language = assignment.option("language", "random")
        if language == "random":
            language = random.choice(tuple(sorted(LANGUAGES)))
        elif language not in LANGUAGES:
            raise ConfigError(
                "creative module language must be chinese, english, or random"
            )
        prompts = load_creative_prompts(settings.library_dir, language)
        with self._lock:
            selected = tuple(random.sample(prompts, 4))
            for _ in range(20):
                if selected != self._last.get(language):
                    break
                selected = tuple(random.sample(prompts, 4))
            self._last[language] = selected
        return json.dumps(
            {"language": language, "items": selected},
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def render(
        self,
        settings: Settings,
        content_id: int | str,
        rect: Rect,
        now: datetime,
    ) -> Image.Image:
        del now
        if not isinstance(content_id, str):
            raise ConfigError("invalid creative snapshot")
        try:
            snapshot = json.loads(content_id)
            language = snapshot["language"]
            items = snapshot["items"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ConfigError("invalid creative snapshot") from exc
        if (
            language not in LANGUAGES
            or not isinstance(items, list)
            or len(items) != 4
            or not all(isinstance(item, str) and item for item in items)
        ):
            raise ConfigError("invalid creative snapshot")

        image = Image.new("L", (rect.width, rect.height), 255)
        draw = ImageDraw.Draw(image)
        title = "用这四个字编故事" if language == "chinese" else "Make a story with all four"
        title_font_path = settings.font if language == "chinese" else settings.latin_font
        title_size = 26 if rect.width >= 500 else 18
        title_font = ImageFont.truetype(str(title_font_path), title_size)
        draw.text((rect.width / 2, 5), title, font=title_font, fill=0, anchor="ma")

        top = title_size + 20
        margin = 12
        gap = 10
        if rect.width >= 500:
            columns, rows = 4, 1
        else:
            columns, rows = 2, 2
        cell_width = (rect.width - 2 * margin - (columns - 1) * gap) / columns
        cell_height = (rect.height - top - margin - (rows - 1) * gap) / rows
        font_path = settings.font if language == "chinese" else settings.latin_font
        font = self._fit_font(draw, items, font_path, cell_width - 14, cell_height - 14)
        for index, item in enumerate(items):
            row, column = divmod(index, columns)
            left = margin + column * (cell_width + gap)
            cell_top = top + row * (cell_height + gap)
            right = left + cell_width
            bottom = cell_top + cell_height
            draw.rounded_rectangle(
                (left, cell_top, right, bottom),
                radius=8,
                outline=0,
                width=2,
            )
            draw.text(
                ((left + right) / 2, (cell_top + bottom) / 2),
                item,
                font=font,
                fill=0,
                anchor="mm",
            )
        return image.point(lambda pixel: 255 if pixel > 180 else 0, mode="1")

    @staticmethod
    def _fit_font(
        draw: ImageDraw.ImageDraw,
        values: list[str],
        font_path: Path,
        max_width: float,
        max_height: float,
    ) -> ImageFont.FreeTypeFont:
        for size in range(int(min(72, max_height * 0.7)), 15, -3):
            font = ImageFont.truetype(str(font_path), size)
            if all(
                (box := draw.textbbox((0, 0), value, font=font))[2] - box[0]
                <= max_width
                for value in values
            ):
                return font
        return ImageFont.truetype(str(font_path), 16)
