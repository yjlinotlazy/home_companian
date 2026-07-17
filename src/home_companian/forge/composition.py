from __future__ import annotations

from datetime import datetime
from typing import Mapping

from PIL import Image

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
    image = Image.new("1", (profile.width, profile.height), 255)
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
    return image
