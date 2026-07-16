from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def render_text(text: str, font_path: Path, size: int = 24) -> Image.Image:
    try:
        font = ImageFont.truetype(str(font_path), size)
    except OSError as exc:
        raise ValueError(f"font cannot be loaded: {font_path}") from exc
    probe = Image.new("L", (1, 1), 255)
    draw = ImageDraw.Draw(probe)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    width = max(1, right - left)
    height = max(1, bottom - top)
    image = Image.new("L", (width, height), 255)
    ImageDraw.Draw(image).text((-left, -top), text, font=font, fill=0)
    return image.point(lambda pixel: 255 if pixel > 180 else 0, mode="1")
