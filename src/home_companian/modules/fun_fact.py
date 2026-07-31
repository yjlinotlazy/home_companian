from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import random
from threading import Lock

from PIL import Image, ImageDraw, ImageFont, ImageOps

from ..config import ConfigError, Settings
from ..domain import Rect, SlotAssignment


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass(frozen=True)
class FunFact:
    name: str
    title: str
    lines: tuple[str, ...]
    image: str | None


def load_fun_facts(library_dir: Path) -> tuple[FunFact, ...]:
    directory = library_dir / "fun_fact"
    try:
        markdown_files = tuple(sorted(directory.glob("*.md")))
    except OSError as exc:
        raise ConfigError(f"fun fact directory cannot be opened: {directory}") from exc
    if not markdown_files:
        raise ConfigError(f"{directory} must contain at least one Markdown file")

    facts: list[FunFact] = []
    for path in markdown_files:
        try:
            raw_lines = path.read_text(encoding="utf-8").splitlines()
            image_candidates = tuple(
                candidate
                for candidate in directory.iterdir()
                if candidate.is_file()
                and candidate.stem == path.stem
                and candidate.suffix.lower() in IMAGE_SUFFIXES
            )
        except OSError as exc:
            raise ConfigError(f"fun fact cannot be opened: {path}") from exc
        if len(image_candidates) > 1:
            raise ConfigError(f"fun fact has multiple matching images: {path.stem}")

        title = path.stem.replace("_", " ").strip()
        content: list[str] = []
        for raw_line in raw_lines:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#"):
                heading = line.lstrip("#").strip()
                if not content and heading:
                    title = heading
                    continue
            if line.startswith(("- ", "* ")):
                line = f"• {line[2:].strip()}"
            if line:
                content.append(line)
        if not title or not content:
            raise ConfigError(f"fun fact Markdown is invalid: {path}")
        facts.append(
            FunFact(
                path.stem,
                title,
                tuple(content),
                image_candidates[0].name if image_candidates else None,
            )
        )
    return tuple(facts)


class FunFactModule:
    name = "fun_fact"

    def __init__(self) -> None:
        self._last_name: str | None = None
        self._lock = Lock()

    def prepare(
        self,
        settings: Settings,
        at: datetime,
        assignment: SlotAssignment,
    ) -> str:
        del at
        if any(key != "name" for key, _ in assignment.options):
            raise ConfigError("fun_fact module only accepts the name option")
        facts = load_fun_facts(settings.library_dir)
        selected_name = assignment.option("name")
        if selected_name is not None:
            fact = next((fact for fact in facts if fact.name == selected_name), None)
            if fact is None:
                raise ConfigError(f"unknown fun fact: {selected_name}")
        else:
            with self._lock:
                candidates = tuple(
                    fact
                    for fact in facts
                    if len(facts) == 1 or fact.name != self._last_name
                )
                fact = random.choice(candidates)
                self._last_name = fact.name
        return json.dumps(
            {
                "type": self.name,
                "name": fact.name,
                "title": fact.title,
                "lines": list(fact.lines),
                "image": fact.image,
            },
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
            raise ConfigError("invalid fun fact snapshot")
        try:
            snapshot = json.loads(content_id)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ConfigError("invalid fun fact snapshot") from exc
        if not isinstance(snapshot, dict):
            raise ConfigError("invalid fun fact snapshot")
        title = snapshot.get("title")
        lines = snapshot.get("lines")
        image_name = snapshot.get("image")
        if (
            snapshot.get("type") != self.name
            or not isinstance(title, str)
            or not title
            or not isinstance(lines, list)
            or not lines
            or not all(isinstance(line, str) and line for line in lines)
            or (
                image_name is not None
                and (
                    not isinstance(image_name, str)
                    or Path(image_name).name != image_name
                    or Path(image_name).suffix.lower() not in IMAGE_SUFFIXES
                )
            )
        ):
            raise ConfigError("invalid fun fact snapshot")

        image = Image.new("L", (rect.width, rect.height), 255)
        draw = ImageDraw.Draw(image)
        title_font_path = (
            settings.font
            if self._contains_cjk(title)
            else settings.latin_font
        )
        title_font = ImageFont.truetype(str(title_font_path), 42)
        draw.text((22, 14), title, font=title_font, fill=0)

        illustration = self._illustration(settings.library_dir, image_name)
        image_width = min(300, rect.width * 2 // 5)
        image_height = min(250, rect.height * 5 // 11)
        illustration_left = rect.width
        illustration_top = rect.height
        if illustration is not None:
            illustration = ImageOps.contain(
                illustration,
                (image_width, image_height),
                Image.Resampling.LANCZOS,
            )
            illustration_left = rect.width - illustration.width - 18
            illustration_top = rect.height - illustration.height - 14
            image.paste(
                illustration,
                (illustration_left, illustration_top),
            )

        body_width = rect.width - 44
        body_top = 74
        body_height = rect.height - body_top - 14
        font, wrapped = self._fit_body(
            draw,
            lines,
            settings.font,
            settings.latin_font,
            body_width,
            body_height,
            max(80, illustration_left - 36),
            max(0, illustration_top - body_top),
        )
        y = body_top
        line_height = round(font.size * 1.35)
        for line in wrapped:
            draw.text((24, y), line, font=font, fill=0)
            y += line_height
        return image

    @staticmethod
    def _illustration(
        library_dir: Path,
        image_name: object,
    ) -> Image.Image | None:
        if image_name is None:
            return None
        path = library_dir / "fun_fact" / str(image_name)
        try:
            with Image.open(path) as source:
                rgba = source.convert("RGBA")
                white = Image.new("RGBA", rgba.size, "white")
                white.alpha_composite(rgba)
                return white.convert("L")
        except OSError as exc:
            raise ConfigError(f"fun fact image cannot be opened: {path}") from exc

    @staticmethod
    def _fit_body(
        draw: ImageDraw.ImageDraw,
        lines: list[str],
        chinese_font_path: Path,
        latin_font_path: Path,
        max_width: int,
        max_height: int,
        lower_width: int,
        lower_start: int,
    ) -> tuple[ImageFont.FreeTypeFont, list[str]]:
        font_path = (
            chinese_font_path
            if any(FunFactModule._contains_cjk(line) for line in lines)
            else latin_font_path
        )
        for size in range(30, 29, -2):
            font = ImageFont.truetype(str(font_path), size)
            line_height = round(size * 1.35)
            if (
                len(lines) * line_height <= max_height
                and all(
                    draw.textlength(line, font=font)
                    <= FunFactModule._line_width(
                        index,
                        line_height,
                        max_width,
                        lower_width,
                        lower_start,
                    )
                    for index, line in enumerate(lines)
                )
            ):
                return font, list(lines)
        for size in range(30, 17, -2):
            font = ImageFont.truetype(str(font_path), size)
            wrapped = FunFactModule._wrap_variable(
                draw,
                lines,
                font,
                max_width,
                lower_width,
                lower_start,
            )
            if len(wrapped) * round(size * 1.35) <= max_height:
                return font, wrapped
        font = ImageFont.truetype(str(font_path), 18)
        return font, FunFactModule._wrap_variable(
            draw,
            lines,
            font,
            max_width,
            lower_width,
            lower_start,
        )

    @staticmethod
    def _contains_cjk(text: str) -> bool:
        return any(
            "\u3400" <= character <= "\u4dbf"
            or "\u4e00" <= character <= "\u9fff"
            or "\uf900" <= character <= "\ufaff"
            or "\u3040" <= character <= "\u30ff"
            or "\uac00" <= character <= "\ud7af"
            for character in text
        )

    @staticmethod
    def _line_width(
        line_index: int,
        line_height: int,
        full_width: int,
        lower_width: int,
        lower_start: int,
    ) -> int:
        return (
            lower_width
            if (line_index + 1) * line_height > lower_start
            else full_width
        )

    @staticmethod
    def _wrap_variable(
        draw: ImageDraw.ImageDraw,
        lines: list[str],
        font: ImageFont.FreeTypeFont,
        full_width: int,
        lower_width: int,
        lower_start: int,
    ) -> list[str]:
        wrapped: list[str] = []
        line_height = round(font.size * 1.35)
        for text in lines:
            words = text.split()
            current = ""
            for word in words:
                candidate = word if not current else f"{current} {word}"
                width = FunFactModule._line_width(
                    len(wrapped),
                    line_height,
                    full_width,
                    lower_width,
                    lower_start,
                )
                if current and draw.textlength(candidate, font=font) > width:
                    wrapped.append(current)
                    current = word
                else:
                    current = candidate
            if current:
                wrapped.append(current)
        return wrapped

    @staticmethod
    def _wrap(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        max_width: int,
    ) -> list[str]:
        words = text.split()
        if not words:
            return []
        wrapped: list[str] = []
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if current and draw.textlength(candidate, font=font) > max_width:
                wrapped.append(current)
                current = word
            else:
                current = candidate
        if current:
            wrapped.append(current)
        return wrapped
