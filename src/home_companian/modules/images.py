from __future__ import annotations

from datetime import datetime
from pathlib import Path, PurePosixPath
import random
import re
from threading import Lock

from PIL import Image

from ..config import ConfigError, Settings
from ..domain import Rect, SlotAssignment


COLLECTION_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


class ImagesModule:
    name = "images"

    def __init__(self) -> None:
        self._last_content_id: str | None = None
        self._lock = Lock()

    def prepare(
        self,
        settings: Settings,
        at: datetime,
        assignment: SlotAssignment,
    ) -> str:
        del at
        collection = assignment.option("collection")
        if collection is None or COLLECTION_NAME.fullmatch(collection) is None:
            raise ConfigError("images module collection must use letters, numbers, _ or -")
        directory = settings.library_dir / "images" / collection
        try:
            files = tuple(
                sorted(
                    path.name
                    for path in directory.iterdir()
                    if path.is_file() and path.suffix.lower() == ".png"
                )
            )
        except OSError as exc:
            raise ConfigError(f"image collection cannot be opened: {directory}") from exc
        if not files:
            raise ConfigError(f"image collection contains no PNG files: {directory}")
        content_ids = tuple(f"{collection}/{name}" for name in files)
        with self._lock:
            candidates = tuple(
                content_id
                for content_id in content_ids
                if len(content_ids) == 1 or content_id != self._last_content_id
            )
            selected = random.choice(candidates)
            self._last_content_id = selected
            return selected

    def render(
        self,
        settings: Settings,
        content_id: int | str,
        rect: Rect,
        now: datetime,
    ) -> Image.Image:
        del now
        path = self._image_path(settings.library_dir, content_id)
        try:
            with Image.open(path) as image:
                if image.format != "PNG":
                    raise ConfigError(f"image asset must be PNG: {path}")
                if image.mode != "1":
                    raise ConfigError(f"image asset must be 1-bit: {path}")
                if image.size != (rect.width, rect.height):
                    raise ConfigError(
                        f"image asset must be {rect.width}x{rect.height}: {path}"
                    )
                return image.copy()
        except OSError as exc:
            raise ConfigError(f"image asset cannot be opened: {path}") from exc

    @staticmethod
    def _image_path(library_dir: Path, content_id: int | str) -> Path:
        if not isinstance(content_id, str):
            raise ConfigError(f"invalid image content id: {content_id}")
        relative = PurePosixPath(content_id)
        if (
            relative.is_absolute()
            or len(relative.parts) != 2
            or any(part in {".", ".."} for part in relative.parts)
            or COLLECTION_NAME.fullmatch(relative.parts[0]) is None
            or Path(relative.parts[1]).suffix.lower() != ".png"
        ):
            raise ConfigError(f"invalid image content id: {content_id}")
        return library_dir / "images" / relative.parts[0] / relative.parts[1]
