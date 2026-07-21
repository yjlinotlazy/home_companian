from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Mapping

from PIL import Image, ImageDraw, ImageOps

from ..config import ConfigError, Settings
from ..devices import DeviceProfile
from ..modules import Module
from ..status_bar import render_status_bar
from ..status_modules import StatusModule
from ..templates import load_template
from .models import Presentation, Scene


def compose_scene(
    scene: Scene,
    presentation: Presentation,
    profile: DeviceProfile,
    settings: Settings,
    now: datetime,
    content_modules: Mapping[str, Module],
    status_modules: Mapping[str, StatusModule],
) -> Image.Image:
    template = load_template(presentation.template)
    if (template.width, template.height) != (profile.width, profile.content_height):
        raise ConfigError(
            f"template {template.id} must be "
            f"{profile.width}x{profile.content_height} for profile {profile.id}"
        )
    fragments = {fragment.id: fragment for fragment in scene.fragments}
    canvas_mode = "L" if profile.grayscale_levels > 2 else "1"
    image = Image.new(canvas_mode, (profile.width, profile.height), 255)
    image.paste(
        render_status_bar(
            settings,
            now,
            status_modules,
            width=profile.width,
            height=profile.status_bar_height,
        ),
        (0, 0),
    )
    for placement in presentation.placements:
        try:
            fragment = fragments[placement.fragment_id]
            rect = template.slot(placement.slot_id)
        except KeyError as exc:
            raise ConfigError(
                f"invalid presentation placement: {placement.fragment_id}"
            ) from exc
        module = content_modules.get(fragment.module)
        if module is None:
            raise ConfigError(f"unknown module: {fragment.module}")
        tile = module.render(settings, fragment.content_id, rect, now)
        image.paste(tile, (rect.x, rect.y + profile.status_bar_height))
    draw = ImageDraw.Draw(image)
    for x1, y1, x2, y2 in template.lines:
        offset = profile.status_bar_height
        draw.line((x1, y1 + offset, x2, y2 + offset), fill=0, width=2)
    _add_kindle_decorations(image, settings.library_dir, profile)
    return image


def _add_kindle_decorations(
    image: Image.Image,
    library_dir: Path,
    profile: DeviceProfile,
) -> None:
    if not profile.id.startswith("kindle_"):
        return

    decorations = (
        (
            "rainbow.png",
            (82, 55),
            (
                image.width // 2 - 94,
                profile.status_bar_height + profile.content_height // 2 - 67,
            ),
        ),
        ("heart_completed.png", (46, 46), (image.width - 58, image.height - 58)),
    )
    for filename, size, position in decorations:
        try:
            with Image.open(library_dir / "decorations" / filename) as source:
                decoration = ImageOps.contain(
                    source.convert("L"),
                    size,
                    Image.Resampling.LANCZOS,
                )
        except OSError:
            continue

        # Treat the drawings' white paper as transparent while preserving gray ink.
        mask = decoration.point(lambda pixel: min(255, (255 - pixel) * 4))
        image.paste(decoration, position, mask)
