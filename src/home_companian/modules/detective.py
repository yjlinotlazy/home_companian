from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFont, ImageOps

from ..config import ConfigError, Settings
from ..detective import DetectiveStore, MAX_HINT_COUNT
from ..domain import Rect, SlotAssignment


class DetectiveModule:
    name = "detective"

    def prepare(
        self,
        settings: Settings,
        at: datetime,
        assignment: SlotAssignment,
    ) -> str:
        del at
        preview = assignment.option("preview") == "true"
        puzzle = DetectiveStore(settings.library_dir).load()
        if len(settings.detective_bulbs) != 3:
            raise ConfigError("detective_bulbs must configure exactly three images")
        return json.dumps(
            {
                "title": puzzle.title,
                "mystery": puzzle.mystery,
                "answer": puzzle.answer,
                "hints": puzzle.hints,
                "visible": puzzle.visible,
                "preview": preview,
                "bulbs": [
                    str(settings.detective_bulbs[index % 3])
                    for index, _ in enumerate(puzzle.hints)
                ],
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
        title, mystery, answer, hints, visible, preview, bulbs = self._snapshot(
            content_id
        )
        image = Image.new("L", (rect.width, rect.height), 255)
        draw = ImageDraw.Draw(image)

        if title:
            title_font = ImageFont.truetype(str(settings.font), 38)
            draw.text(
                (rect.width / 2, 12),
                title,
                font=title_font,
                fill=0,
                anchor="ma",
            )

        top = 70 if title else 12
        bottom = rect.height - 12
        left = 14
        gap = 14
        left_width = round(rect.width * 0.47)
        right_x = left + left_width + gap
        right_width = rect.width - right_x - 14
        divider_y = (top + bottom) // 2 - 20
        mystery_box = (left, top, left + left_width, divider_y - 6)
        answer_box = (left, divider_y + 6, left + left_width, bottom)
        hints_box = (right_x, top, right_x + right_width, bottom)

        draw.rounded_rectangle(mystery_box, radius=4, outline=0, width=2)
        draw.rounded_rectangle(answer_box, radius=4, outline=0, width=2)
        draw.rounded_rectangle(hints_box, radius=4, outline=0, width=2)
        self._draw_fitted_text(
            draw,
            mystery,
            (left + 12, top + 8, left + left_width - 12, divider_y - 16),
            settings.font,
            24,
            15,
        )
        self._draw_fitted_text(
            draw,
            answer,
            (left + 12, divider_y + 14, left + left_width - 12, bottom - 8),
            settings.font,
            24,
            15,
        )
        self._draw_hints(
            image,
            hints_box,
            hints,
            visible,
            preview,
            bulbs,
            settings.font,
        )
        return image

    @classmethod
    def _draw_hints(
        cls,
        image: Image.Image,
        box: tuple[int, int, int, int],
        hints: tuple[str, ...],
        visible: tuple[bool, ...],
        preview: bool,
        bulbs: tuple[Path, ...],
        font_path: Path,
    ) -> None:
        draw = ImageDraw.Draw(image)
        content_top = box[1] + 8
        available_height = box[3] - content_top - 8
        row_height = max(17, available_height // max(1, len(hints)))
        icon_size = min(34, max(15, row_height - 5))
        font_size = min(23, max(12, row_height - 8))
        font = ImageFont.truetype(str(font_path), font_size)
        x = box[0] + 10
        text_x = x + icon_size + 8
        text_width = box[2] - text_x - 10
        for index, (hint, is_visible, bulb_path) in enumerate(
            zip(hints, visible, bulbs, strict=True)
        ):
            y = content_top + index * row_height
            icon_y = y + (row_height - icon_size) // 2
            cls._paste_bulb(image, bulb_path, (x, icon_y), icon_size)
            rendered_hint = hint if is_visible or preview else ""
            lines = cls._wrap(draw, rendered_hint, font, text_width)[:2]
            draw.multiline_text(
                (text_x, y + row_height / 2),
                "\n".join(lines),
                font=font,
                fill=0 if is_visible else 128,
                spacing=1,
                anchor="lm",
            )

    @staticmethod
    def _paste_bulb(
        image: Image.Image,
        path: Path,
        position: tuple[int, int],
        size: int,
    ) -> None:
        try:
            with Image.open(path) as source:
                rgba = source.convert("RGBA")
                bulb = ImageOps.contain(rgba, (size, size), Image.Resampling.LANCZOS)
        except OSError as exc:
            raise ConfigError(f"detective bulb image cannot be opened: {path}") from exc
        image.paste(bulb.convert("L"), position, bulb.getchannel("A"))

    @classmethod
    def _draw_fitted_text(
        cls,
        draw: ImageDraw.ImageDraw,
        text: str,
        box: tuple[int, int, int, int],
        font_path: Path,
        maximum_size: int,
        minimum_size: int,
    ) -> None:
        width = box[2] - box[0]
        height = box[3] - box[1]
        lines: list[str] = []
        for size in range(maximum_size, minimum_size - 1, -1):
            font = ImageFont.truetype(str(font_path), size)
            lines = cls._wrap(draw, text, font, width)
            line_height = round(size * 1.3)
            if len(lines) * line_height <= height:
                break
        draw.multiline_text(
            (box[0], box[1]),
            "\n".join(lines),
            font=font,
            fill=0,
            spacing=max(2, size // 5),
        )

    @staticmethod
    def _wrap(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        width: int,
    ) -> list[str]:
        lines: list[str] = []
        for paragraph in text.splitlines() or [""]:
            current = ""
            for token in re.findall(r"[A-Za-z0-9]+(?:['’_-][A-Za-z0-9]+)*|\s+|.", paragraph):
                if token.isspace():
                    token = " " if current else ""
                candidate = current + token
                if current and draw.textlength(candidate, font=font) > width:
                    lines.append(current.rstrip())
                    current = token.lstrip()
                else:
                    current = candidate
            lines.append(current.rstrip())
        return lines or [""]

    @staticmethod
    def _snapshot(
        content_id: int | str,
    ) -> tuple[
        str,
        str,
        str,
        tuple[str, ...],
        tuple[bool, ...],
        bool,
        tuple[Path, ...],
    ]:
        if not isinstance(content_id, str):
            raise ConfigError("invalid detective snapshot")
        try:
            raw = json.loads(content_id)
            title = raw["title"]
            mystery = raw["mystery"]
            answer = raw["answer"]
            hints = raw["hints"]
            visible = raw["visible"]
            preview = raw["preview"]
            bulbs = raw["bulbs"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ConfigError("invalid detective snapshot") from exc
        if (
            not isinstance(title, str)
            or not isinstance(mystery, str)
            or not isinstance(answer, str)
            or not isinstance(hints, list)
            or not 1 <= len(hints) <= MAX_HINT_COUNT
            or not all(isinstance(hint, str) for hint in hints)
            or not isinstance(visible, list)
            or len(visible) != len(hints)
            or not all(type(value) is bool for value in visible)
            or type(preview) is not bool
            or not isinstance(bulbs, list)
            or len(bulbs) != len(hints)
            or not all(isinstance(path, str) and path for path in bulbs)
        ):
            raise ConfigError("invalid detective snapshot")
        return (
            title,
            mystery,
            answer,
            tuple(hints),
            tuple(visible),
            preview,
            tuple(Path(path) for path in bulbs),
        )
