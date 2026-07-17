from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json

from ..domain import PanelConfig


@dataclass(frozen=True)
class SceneFragment:
    id: str
    module: str
    content_id: int | str
    role: str


@dataclass(frozen=True)
class Scene:
    id: str
    fragments: tuple[SceneFragment, ...]
    target_at: datetime | None = None

    @classmethod
    def create(
        cls,
        fragments: tuple[SceneFragment, ...],
        target_at: datetime | None = None,
    ) -> "Scene":
        semantic = {
            "fragments": [
                {
                    "id": fragment.id,
                    "module": fragment.module,
                    "content_id": fragment.content_id,
                    "role": fragment.role,
                }
                for fragment in fragments
            ],
            "target_at": target_at.isoformat() if target_at else None,
        }
        scene_id = sha256(
            json.dumps(semantic, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        return cls(scene_id, fragments, target_at)


@dataclass(frozen=True)
class Placement:
    slot_id: int
    fragment_id: str


@dataclass(frozen=True)
class Presentation:
    id: str
    template: str
    placements: tuple[Placement, ...]

    @classmethod
    def from_panel(cls, panel: PanelConfig) -> "Presentation":
        placements = tuple(
            Placement(assignment.slot_id, f"fragment-{index}")
            for index, assignment in enumerate(panel.slots)
        )
        return cls(panel.template, panel.template, placements)


@dataclass(frozen=True)
class Frame:
    id: str
    scene_id: str
    profile_id: str
    mime_type: str
    payload: bytes
    payload_hash: str
    created_at: datetime
