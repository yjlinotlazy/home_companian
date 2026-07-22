from __future__ import annotations

from datetime import datetime
from pathlib import Path, PurePosixPath
import random
import re
from threading import Lock

from PIL import Image

from ..config import ConfigError, Settings
from ..domain import Rect, SlotAssignment
from ..image_processing import process_image


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
        collections_option = assignment.option("collections")
        if collection is not None and collections_option is not None:
            raise ConfigError("images module must use collection or collections, not both")
        wildcard = collections_option == "*"
        if wildcard:
            root = settings.library_dir / "images"
            try:
                collections = tuple(
                    sorted(
                        path.name
                        for path in root.iterdir()
                        if path.is_dir()
                        and path.name != "raw"
                        and COLLECTION_NAME.fullmatch(path.name) is not None
                    )
                )
            except OSError as exc:
                raise ConfigError(f"image library cannot be opened: {root}") from exc
        elif collections_option is not None:
            collections = tuple(
                dict.fromkeys(part.strip() for part in collections_option.split(","))
            )
        elif collection is not None:
            collections = (collection,)
        else:
            collections = ()
        if not collections or any(
            COLLECTION_NAME.fullmatch(name) is None for name in collections
        ):
            raise ConfigError(
                "images module collections must be * or use comma-separated "
                "letters, numbers, _ or -"
            )

        content_ids: list[str] = []
        for name in collections:
            directory = settings.library_dir / "images" / name
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
            if not files and wildcard:
                continue
            if not files:
                raise ConfigError(f"image collection contains no PNG files: {directory}")
            content_ids.extend(f"{name}/{filename}" for filename in files)
        if not content_ids:
            raise ConfigError("image collections contain no PNG files")
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
        path = self._kindle_grayscale_path(settings, path)
        try:
            with Image.open(path) as image:
                return process_image(
                    image,
                    size=(rect.width, rect.height),
                    fit="contain",
                    binarize="grayscale",
                )
        except OSError as exc:
            raise ConfigError(f"image asset cannot be opened: {path}") from exc

    @staticmethod
    def _kindle_grayscale_path(settings: Settings, path: Path) -> Path:
        if not settings.profile_id.startswith("kindle_") or path.stem.endswith("_grey"):
            return path
        grayscale_stem = f"{path.stem}_grey"
        try:
            candidates = sorted(
                candidate
                for candidate in path.parent.iterdir()
                if candidate.is_file() and candidate.stem == grayscale_stem
            )
        except OSError:
            return path
        return candidates[0] if candidates else path

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
