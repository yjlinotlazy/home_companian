from __future__ import annotations

from pathlib import Path
import unicodedata

from PIL import Image, ImageDraw, ImageFont


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


def render_centered_text(
    text: str,
    chinese_path: Path,
    latin_path: Path,
    size: tuple[int, int],
) -> Image.Image:
    image = Image.new("L", size, 255)
    draw = ImageDraw.Draw(image)
    chinese_font, latin_font = _content_fonts(
        draw, text, chinese_path, latin_path, size[0]
    )
    text_width, top, bottom = _mixed_metrics(
        draw, text, chinese_font, latin_font
    )
    x = (size[0] - text_width) / 2
    baseline = (size[1] - (bottom - top)) / 2 - top
    for run, chinese in _text_runs(text):
        font = chinese_font if chinese else latin_font
        draw.text((x, baseline), run, font=font, fill=0, anchor="ls")
        x += draw.textlength(run, font=font)
    return image.point(lambda pixel: 255 if pixel > THRESHOLD else 0, mode="1")
