from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import Item


VISIBLE_WIDTH = 792
MEMORY_WIDTH = 800
HEIGHT = 272
SEAM_X = 396
FRAMEBUFFER_SIZE = MEMORY_WIDTH * HEIGHT // 8
THRESHOLD = 180


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(path), size)
    except OSError as exc:
        raise ValueError(f"font cannot be loaded: {path}") from exc


def _centered_x(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    return (VISIBLE_WIDTH - (right - left)) // 2 - left


def render_scene(
    item: Item,
    font_path: Path,
    battery: int | None = None,
    now: datetime | None = None,
) -> Image.Image:
    now = now or datetime.now()
    image = Image.new("L", (VISIBLE_WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(image)

    status_font = _font(font_path, 24)
    title_font = _font(font_path, 64)
    description_font = _font(font_path, 30)

    battery_text = "电量 --%" if battery is None else f"电量 {battery}%"
    time_text = now.strftime("%H:%M")
    status_right = f"{battery_text}    {time_text}"
    bounds = draw.textbbox((0, 0), status_right, font=status_font)
    draw.text((VISIBLE_WIDTH - (bounds[2] - bounds[0]) - 16, 7), status_right, font=status_font, fill=0)

    title_y = 84 if item.description else 105
    draw.text((_centered_x(draw, item.title, title_font), title_y), item.title, font=title_font, fill=0)
    if item.description:
        draw.text(
            (_centered_x(draw, item.description, description_font), 183),
            item.description,
            font=description_font,
            fill=0,
        )

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
