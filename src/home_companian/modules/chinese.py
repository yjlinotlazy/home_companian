from __future__ import annotations

from datetime import datetime
from pathlib import Path
import random
import re
from threading import Lock

from PIL import Image, ImageDraw, ImageFont

from ..config import ConfigError, Settings
from ..domain import Rect, SlotAssignment


GRADE_HEADING = re.compile(r"^#+\s*([一二三四五六])年级\s*$")
EXPECTED_GRADES = set("一二三四五六")


def load_chinese_characters(library_dir: Path) -> tuple[str, ...]:
    full_path = library_dir / "chinese" / "full.md"
    select_path = library_dir / "chinese" / "select.md"
    full, grades = _read_full(full_path)
    if grades != EXPECTED_GRADES:
        raise ConfigError("chinese/full.md must contain headings for grades 一 through 六")
    selected = _read_characters(select_path)
    if not selected:
        raise ConfigError("chinese/select.md must contain at least one character")
    unknown = [character for character in selected if character not in set(full)]
    if unknown:
        raise ConfigError(f"chinese/select.md contains character not in full.md: {unknown[0]}")
    return selected


def _read_full(path: Path) -> tuple[tuple[str, ...], set[str]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ConfigError(f"Chinese character file cannot be opened: {path}") from exc
    grades: set[str] = set()
    content: list[str] = []
    for line in lines:
        if line.lstrip().startswith("#"):
            match = GRADE_HEADING.fullmatch(line.strip())
            if match is None:
                raise ConfigError(f"invalid grade heading in {path}: {line.strip()}")
            grades.add(match.group(1))
        else:
            content.append(line)
    return _characters("\n".join(content), path), grades


def _read_characters(path: Path) -> tuple[str, ...]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Chinese character file cannot be opened: {path}") from exc
    return _characters(text, path)


def _characters(text: str, path: Path) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for character in text:
        if character.isspace():
            continue
        if not _is_han(character):
            raise ConfigError(f"{path} contains non-Chinese character: {character}")
        if character not in seen:
            result.append(character)
            seen.add(character)
    return tuple(result)


def _is_han(character: str) -> bool:
    codepoint = ord(character)
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0x20000 <= codepoint <= 0x323AF
    )


class ChineseModule:
    name = "chinese"

    def __init__(self) -> None:
        self._last_character: str | None = None
        self._lock = Lock()

    def prepare(
        self,
        settings: Settings,
        at: datetime,
        assignment: SlotAssignment,
    ) -> str:
        del at
        if assignment.option("source", "select") != "select":
            raise ConfigError("chinese module source must be select")
        characters = load_chinese_characters(settings.library_dir)
        with self._lock:
            candidates = [
                character
                for character in characters
                if len(characters) == 1 or character != self._last_character
            ]
            selected = random.choice(candidates)
            self._last_character = selected
            return selected

    def render(
        self,
        settings: Settings,
        content_id: int | str,
        rect: Rect,
        now: datetime,
    ) -> Image.Image:
        del now
        if not isinstance(content_id, str) or len(content_id) != 1:
            raise ValueError(f"invalid Chinese content id: {content_id}")
        image = Image.new("L", (rect.width, rect.height), 255)
        draw = ImageDraw.Draw(image)
        size = max(20, min(rect.width, rect.height) - 40)
        font = ImageFont.truetype(str(settings.font), size)
        left, top, right, bottom = draw.textbbox((0, 0), content_id, font=font)
        x = (rect.width - (right - left)) / 2 - left
        y = (rect.height - (bottom - top)) / 2 - top
        draw.text((x, y), content_id, font=font, fill=0)
        return image.point(lambda pixel: 255 if pixel > 180 else 0, mode="1")


class ChineseCharactersModule:
    """Display a five-character recognition exercise."""

    name = "chinese_characters"

    def __init__(self) -> None:
        self._last_characters: tuple[str, ...] | None = None
        self._lock = Lock()

    def prepare(
        self,
        settings: Settings,
        at: datetime,
        assignment: SlotAssignment,
    ) -> str:
        del at, assignment
        characters = load_chinese_characters(settings.library_dir)
        if len(characters) < 5:
            raise ConfigError("chinese/select.md must contain at least five characters")
        with self._lock:
            for _ in range(20):
                selected = tuple(random.sample(characters, 5))
                if selected != self._last_characters:
                    self._last_characters = selected
                    return "".join(selected)
        raise ConfigError("could not generate a new five-character exercise")

    def render(
        self,
        settings: Settings,
        content_id: int | str,
        rect: Rect,
        now: datetime,
    ) -> Image.Image:
        del now
        if not isinstance(content_id, str) or len(content_id) != 5:
            raise ConfigError("invalid five-character Chinese content id")
        image = Image.new("L", (rect.width, rect.height), 255)
        draw = ImageDraw.Draw(image)
        cell_width = rect.width / 5
        size = max(20, min(120, rect.height - 40, int(cell_width - 20)))
        font = ImageFont.truetype(str(settings.font), size)
        for index, character in enumerate(content_id):
            left = index * cell_width
            bounds = draw.textbbox((0, 0), character, font=font)
            x = left + (cell_width - (bounds[2] - bounds[0])) / 2 - bounds[0]
            y = (rect.height - (bounds[3] - bounds[1])) / 2 - bounds[1]
            draw.text((x, y), character, font=font, fill=0)
        return image.point(lambda pixel: 255 if pixel > 180 else 0, mode="1")
