from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Mapping

from PIL import Image

from ..config import ConfigError, Settings
from ..devices import DeviceProfile
from ..modules import Module
from ..status_modules import StatusModule
from .composition import compose_scene
from .encoders import CrowPanel1BitEncoder, Encoder, PngEncoder
from .models import Frame, Presentation, Scene


@dataclass(frozen=True)
class ForgeOutput:
    image: Image.Image
    frame: Frame


class Forge:
    def __init__(self, encoders: Mapping[str, Encoder] | None = None) -> None:
        self.encoders = dict(
            encoders
            or {
                CrowPanel1BitEncoder.name: CrowPanel1BitEncoder(),
                PngEncoder.name: PngEncoder(),
            }
        )

    def render(
        self,
        scene: Scene,
        presentation: Presentation,
        profile: DeviceProfile,
        settings: Settings,
        now: datetime,
        content_modules: Mapping[str, Module],
        status_modules: Mapping[str, StatusModule],
    ) -> ForgeOutput:
        image = compose_scene(
            scene,
            presentation,
            profile,
            settings,
            now,
            content_modules,
            status_modules,
        )
        frame = self.encode(image, scene.id, profile, now)
        return ForgeOutput(image, frame)

    def encode(
        self,
        image: Image.Image,
        scene_id: str,
        profile: DeviceProfile,
        created_at: datetime,
    ) -> Frame:
        encoder = self.encoders.get(profile.encoder)
        if encoder is None:
            raise ConfigError(f"unknown frame encoder: {profile.encoder}")
        payload = encoder.encode(image, profile)
        payload_hash = sha256(payload).hexdigest()
        frame_id = sha256(
            f"{scene_id}:{profile.id}:{payload_hash}".encode("utf-8")
        ).hexdigest()
        return Frame(
            id=frame_id,
            scene_id=scene_id,
            profile_id=profile.id,
            mime_type=profile.mime_type,
            payload=payload,
            payload_hash=payload_hash,
            created_at=created_at,
        )
