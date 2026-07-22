from __future__ import annotations

from datetime import datetime
import json
import re

from PIL import Image, ImageDraw, ImageFont, ImageOps

from ..config import ConfigError, Settings
from ..domain import Rect, SlotAssignment
from ..treasure_hunt import TEXT_BOX_COUNT, TreasureHuntStore


CHECK_WIDTH_RATIO = 0.28
CHECK_HEIGHT_RATIO = 0.18


class TreasureHuntModule:
    name = "treasure_hunt"

    def prepare(
        self,
        settings: Settings,
        at: datetime,
        assignment: SlotAssignment,
    ) -> str:
        del at, assignment
        hunt = TreasureHuntStore(settings.library_dir).load()
        return json.dumps(
            {
                "background": hunt.background.name,
                "boxes": hunt.background.boxes,
                "texts": hunt.texts,
                "completed": hunt.completed,
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
        background_name, boxes, texts, completed = self._snapshot(content_id)
        store = TreasureHuntStore(settings.library_dir)
        path = store.background_path(background_name)
        try:
            with Image.open(path) as source:
                rgba = source.convert("RGBA")
                white = Image.new("RGBA", rgba.size, "white")
                white.alpha_composite(rgba)
                background = ImageOps.contain(
                    white.convert("L"),
                    (rect.width, rect.height),
                    Image.Resampling.LANCZOS,
                )
        except OSError as exc:
            raise ConfigError(f"treasure hunt background cannot be opened: {path}") from exc

        image = Image.new("L", (rect.width, rect.height), 255)
        offset = (
            (rect.width - background.width) // 2,
            (rect.height - background.height) // 2,
        )
        image.paste(background, offset)
        for is_completed, box in zip(completed, boxes, strict=True):
            if is_completed:
                self._draw_check(
                    image,
                    background.size,
                    offset,
                    box,
                    store.check_path(),
                )
        for text, box in zip(texts, boxes, strict=True):
            self._draw_text(image, background.size, offset, box, text, settings.font)
        return image

    @staticmethod
    def _snapshot(
        content_id: int | str,
    ) -> tuple[
        str,
        tuple[tuple[float, float, float, float], ...],
        tuple[str, ...],
        tuple[bool, ...],
    ]:
        if not isinstance(content_id, str):
            raise ConfigError(f"invalid treasure hunt snapshot: {content_id}")
        try:
            raw = json.loads(content_id)
            background = raw["background"]
            raw_boxes = raw["boxes"]
            raw_texts = raw["texts"]
            raw_completed = raw["completed"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ConfigError("invalid treasure hunt snapshot") from exc
        if (
            not isinstance(background, str)
            or not isinstance(raw_boxes, list)
            or len(raw_boxes) != TEXT_BOX_COUNT
            or not isinstance(raw_texts, list)
            or len(raw_texts) != TEXT_BOX_COUNT
            or not all(isinstance(text, str) for text in raw_texts)
            or not isinstance(raw_completed, list)
            or len(raw_completed) != TEXT_BOX_COUNT
            or not all(type(value) is bool for value in raw_completed)
        ):
            raise ConfigError("invalid treasure hunt snapshot")
        boxes: list[tuple[float, float, float, float]] = []
        for box in raw_boxes:
            if (
                not isinstance(box, list)
                or len(box) != 4
                or not all(type(value) in {int, float} for value in box)
            ):
                raise ConfigError("invalid treasure hunt snapshot")
            x, y, width, height = (float(value) for value in box)
            if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1 or y + height > 1:
                raise ConfigError("invalid treasure hunt snapshot")
            boxes.append((x, y, width, height))
        return background, tuple(boxes), tuple(raw_texts), tuple(raw_completed)

    @staticmethod
    def _draw_check(
        image: Image.Image,
        background_size: tuple[int, int],
        offset: tuple[int, int],
        box: tuple[float, float, float, float],
        check_path,
    ) -> None:
        background_width, background_height = background_size
        x, y, width, height = box
        box_width = max(1, round(width * background_width))
        box_height = max(1, round(height * background_height))
        check_bounds = (
            max(1, round(background_width * CHECK_WIDTH_RATIO)),
            max(1, round(background_height * CHECK_HEIGHT_RATIO)),
        )
        try:
            with Image.open(check_path) as source:
                check = ImageOps.contain(
                    source.convert("RGBA"),
                    check_bounds,
                    Image.Resampling.LANCZOS,
                )
        except OSError as exc:
            raise ConfigError(
                f"treasure hunt check image cannot be opened: {check_path}"
            ) from exc
        position = (
            offset[0] + round(x * background_width) + (box_width - check.width) // 2,
            offset[1] + round(y * background_height) + (box_height - check.height) // 2,
        )
        image.paste(check.convert("L"), position, check.getchannel("A"))

    @classmethod
    def _draw_text(
        cls,
        image: Image.Image,
        background_size: tuple[int, int],
        offset: tuple[int, int],
        box: tuple[float, float, float, float],
        text: str,
        font_path,
    ) -> None:
        if not text:
            return
        background_width, background_height = background_size
        x, y, width, height = box
        box_width = max(1, round(width * background_width))
        box_height = max(1, round(height * background_height))
        target_x = offset[0] + round(x * background_width)
        target_y = offset[1] + round(y * background_height)
        canvas = image.crop(
            (target_x, target_y, target_x + box_width, target_y + box_height)
        )
        draw = ImageDraw.Draw(canvas)
        padding = max(4, round(box_width * 0.02))
        usable_width = box_width - padding * 2
        maximum_font_size = min(36, max(18, box_height // 3))
        lines = None
        explicit_lines = [line.strip() for line in text.splitlines()]
        for font_size in range(maximum_font_size, 19, -1):
            font = ImageFont.truetype(str(font_path), font_size)
            spacing = max(3, font_size // 5)
            bounds = draw.multiline_textbbox(
                (0, 0),
                "\n".join(explicit_lines),
                font=font,
                spacing=spacing,
                align="left",
            )
            if (
                all(
                    draw.textlength(line, font=font) <= usable_width
                    for line in explicit_lines
                )
                and bounds[3] - bounds[1] <= box_height
            ):
                lines = explicit_lines
                break
        if lines is None:
            for font_size in range(maximum_font_size, 15, -1):
                font = ImageFont.truetype(str(font_path), font_size)
                lines = cls._wrap_text(draw, text, font, usable_width)
                spacing = max(3, font_size // 5)
                bounds = draw.multiline_textbbox(
                    (0, 0),
                    "\n".join(lines),
                    font=font,
                    spacing=spacing,
                    align="left",
                )
                text_height = bounds[3] - bounds[1]
                if text_height <= box_height and not cls._starts_with_short_connector(
                    lines
                ):
                    break
        draw.multiline_text(
            (padding, box_height / 2),
            "\n".join(lines),
            font=font,
            fill=0,
            spacing=spacing,
            align="left",
            anchor="lm",
        )
        image.paste(
            canvas,
            (target_x, target_y),
        )

    @staticmethod
    def _wrap_text(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        width: int,
    ) -> list[str]:
        lines: list[str] = []
        for paragraph in text.splitlines() or [""]:
            line = ""
            pending_space = ""
            tokens = re.findall(
                r"[A-Za-z0-9]+(?:['’_-][A-Za-z0-9]+)*|\s+|.",
                paragraph,
            )
            for token in tokens:
                if token.isspace():
                    pending_space = " " if line else ""
                    continue
                candidate = line + pending_space + token
                if line and draw.textlength(candidate, font=font) > width:
                    lines.append(line.rstrip())
                    line = ""
                    pending_space = ""
                candidate = line + pending_space + token
                if draw.textlength(candidate, font=font) <= width:
                    line = candidate
                    pending_space = ""
                    continue
                for character in token:
                    candidate = line + character
                    if line and draw.textlength(candidate, font=font) > width:
                        lines.append(line.rstrip())
                        line = character
                    else:
                        line = candidate
                pending_space = ""
            lines.append(line.rstrip())
        return lines or [""]

    @staticmethod
    def _starts_with_short_connector(lines: list[str]) -> bool:
        connectors = {
            "A",
            "AN",
            "AT",
            "BY",
            "IN",
            "OF",
            "ON",
            "OR",
            "THE",
            "TO",
        }
        return any(
            line.split(maxsplit=1)[0].upper() in connectors
            for line in lines[1:]
            if line
        )
