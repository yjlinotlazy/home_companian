from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps


DEFAULT_SIZE = (792, 228)
DEFAULT_THRESHOLD = 180


def process_image(
    image: Image.Image,
    *,
    size: tuple[int, int] = DEFAULT_SIZE,
    fit: str = "cover",
    binarize: str = "dither",
    threshold: int = DEFAULT_THRESHOLD,
    autocontrast: bool = False,
    invert: bool = False,
    trim: int = 0,
    content_scale: float = 1.0,
) -> Image.Image:
    """Convert an image into a slot-sized e-ink asset."""
    width, height = size
    if width <= 0 or height <= 0:
        raise ValueError("image size must be positive")
    if fit not in {"cover", "contain"}:
        raise ValueError("fit must be cover or contain")
    if binarize not in {"dither", "threshold", "grayscale"}:
        raise ValueError("binarize must be dither, threshold, or grayscale")
    if not 0 <= threshold <= 255:
        raise ValueError("threshold must be between 0 and 255")
    if trim < 0:
        raise ValueError("trim must not be negative")
    if not 0 < content_scale <= 1:
        raise ValueError("content scale must be greater than 0 and at most 1")

    oriented = ImageOps.exif_transpose(image)
    if trim:
        if trim * 2 >= min(oriented.size):
            raise ValueError("trim removes the entire image")
        oriented = oriented.crop(
            (trim, trim, oriented.width - trim, oriented.height - trim)
        )
    rgba = oriented.convert("RGBA")
    white = Image.new("RGBA", rgba.size, "white")
    white.alpha_composite(rgba)
    grayscale = white.convert("L")

    content_size = (
        max(1, round(width * content_scale)),
        max(1, round(height * content_scale)),
    )
    if fit == "cover":
        content = ImageOps.fit(
            grayscale, content_size, method=Image.Resampling.LANCZOS
        )
    else:
        content = ImageOps.contain(
            grayscale, content_size, method=Image.Resampling.LANCZOS
        )
    fitted = Image.new("L", size, 255)
    fitted.paste(
        content,
        ((width - content.width) // 2, (height - content.height) // 2),
    )

    if autocontrast:
        fitted = ImageOps.autocontrast(fitted)
    if invert:
        fitted = ImageOps.invert(fitted)
    if binarize == "grayscale":
        return fitted
    if binarize == "threshold":
        return fitted.point(lambda pixel: 255 if pixel > threshold else 0, mode="1")
    return fitted.convert("1", dither=Image.Dither.FLOYDSTEINBERG)


def process_file(
    source: Path,
    output: Path,
    **options: object,
) -> Image.Image:
    if output.suffix.lower() != ".png":
        raise ValueError("output file must use the .png extension")
    try:
        with Image.open(source) as image:
            processed = process_image(image, **options)
    except OSError as exc:
        raise ValueError(f"input image cannot be opened: {source}") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    processed.save(output, format="PNG", optimize=True)
    return processed
