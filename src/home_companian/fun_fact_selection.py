from __future__ import annotations

import os
from pathlib import Path
import tempfile
from threading import Lock

import yaml

from .config import ConfigError


_LOCK = Lock()


class FunFactSelectionStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def selected(self) -> str | None:
        if not self.path.exists():
            return None
        try:
            raw = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigError(f"fun fact selection cannot be opened: {self.path}") from exc
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
            raise ConfigError("fun fact selection state is invalid")
        return raw["name"]

    def select(self, name: str) -> None:
        with _LOCK:
            temporary_path: Path | None = None
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    "w",
                    encoding="utf-8",
                    dir=self.path.parent,
                    prefix=f".{self.path.name}.",
                    suffix=".yaml",
                    delete=False,
                ) as handle:
                    temporary_path = Path(handle.name)
                    yaml.safe_dump({"name": name}, handle, sort_keys=False)
                os.replace(temporary_path, self.path)
            except OSError as exc:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
                raise ConfigError(
                    f"fun fact selection cannot be updated: {self.path}"
                ) from exc
