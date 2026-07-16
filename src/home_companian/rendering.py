from __future__ import annotations

from datetime import datetime
from pathlib import Path
import unicodedata

from PIL import Image, ImageDraw, ImageFont

from .config import Item


VISIBLE_WIDTH = 792
MEMORY_WIDTH = 800
HEIGHT = 272
STATUS_BAR_HEIGHT = 44
CONTENT_HEIGHT = HEIGHT - STATUS_BAR_HEIGHT
SEAM_X = 396
FRAMEBUFFER_SIZE = MEMORY_WIDTH * HEIGHT // 8
THRESHOLD = 180


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(path), size)
    except OSError as exc:
        raise ValueError(f"font cannot be loaded: {path}") from exc


def _uses_chinese_font(character: str) -> bool:
    return unicodedata.east_asian_width(character) in {"W", "F"}


def _text_runs(text: str) -> list[tuple[str, bool]]:
    runs: list[tuple[str, bool]] = []
    for character in text:
        chinese = _uses_chinese_font(character)
        if runs and runs[-1][1] == chinese:
            runs[-1] = (runs[-1][0] + character, chinese)
        else:
            runs.append((character, chinese))
    return runs


def _mixed_metrics(
    draw: ImageDraw.ImageDraw,
    text: str,
    chinese_font: ImageFont.FreeTypeFont,
    latin_font: ImageFont.FreeTypeFont,
) -> tuple[float, int, int]:
    width = 0.0
    top = 0
    bottom = 0
    for run, chinese in _text_runs(text):
        font = chinese_font if chinese else latin_font
        bounds = draw.textbbox((0, 0), run, font=font, anchor="ls")
        width += draw.textlength(run, font=font)
        top = min(top, bounds[1])
        bottom = max(bottom, bounds[3])
    return width, top, bottom


def _content_fonts(
    draw: ImageDraw.ImageDraw,
    text: str,
    chinese_path: Path,
    latin_path: Path,
    available_width: int,
) -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    for size in range(64, 27, -4):
        chinese_font = _font(chinese_path, size)
        latin_font = _font(latin_path, size)
        width, _, _ = _mixed_metrics(draw, text, chinese_font, latin_font)
        if width <= max(1, available_width - 64):
            return chinese_font, latin_font
    return _font(chinese_path, 28), _font(latin_path, 28)


def render_scene(
    item: Item,
    font_path: Path,
    latin_font_path: Path | None = None,
    now: datetime | None = None,
    size: tuple[int, int] = (VISIBLE_WIDTH, CONTENT_HEIGHT),
) -> Image.Image:
    del now
    latin_font_path = latin_font_path or font_path
    width, height = size
    image = Image.new("L", size, 255)
    draw = ImageDraw.Draw(image)

    chinese_font, latin_font = _content_fonts(
        draw, item.text, font_path, latin_font_path, width
    )

    text_width, top, bottom = _mixed_metrics(draw, item.text, chinese_font, latin_font)
    x = (size[0] - text_width) / 2
    baseline = (height - (bottom - top)) / 2 - top
    for run, chinese in _text_runs(item.text):
        font = chinese_font if chinese else latin_font
        draw.text((x, baseline), run, font=font, fill=0, anchor="ls")
        x += draw.textlength(run, font=font)

    return image.point(lambda pixel: 255 if pixel > THRESHOLD else 0, mode="1")


def image_to_framebuffer(image: Image.Image) -> bytes:
    if image.size != (VISIBLE_WIDTH, HEIGHT):
        raise ValueError(f"image must be {VISIBLE_WIDTH}x{HEIGHT}, got {image.width}x{image.height}")

    monochrome = image.convert("L").point(lambda pixel: 255 if pixel > THRESHOLD else 0)
    framebuffer = bytearray([0xFF] * FRAMEBUFFER_SIZE)

    for visible_y in range(HEIGHT):
        for visible_x in range(VISIBLE_WIDTH):
            if monochrome.getpixel((visible_x, visible_y)) != 0:
                continue
            memory_x = visible_x + (8 if visible_x >= SEAM_X else 0)
            memory_x = MEMORY_WIDTH - memory_x - 1
            memory_y = HEIGHT - visible_y - 1
            offset = memory_y * (MEMORY_WIDTH // 8) + memory_x // 8
            framebuffer[offset] &= ~(0x80 >> (memory_x % 8))

    return bytes(framebuffer)
