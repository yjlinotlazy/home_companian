from __future__ import annotations

from datetime import date
from pathlib import Path
import os
import tempfile
from threading import Lock

import yaml

from .config import ConfigError


TASKBOARD_MODE = "taskboard"
TREASURE_HUNT_MODE = "treasure_hunt"
DISPLAY_MODES = frozenset({TASKBOARD_MODE, TREASURE_HUNT_MODE})
_MODE_LOCK = Lock()


class DisplayModeStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def selected(self, today: date) -> str:
        if not self.path.exists():
            return TASKBOARD_MODE
        try:
            raw = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigError(f"display mode cannot be opened: {self.path}") from exc
        if not isinstance(raw, dict):
            raise ConfigError("display mode state must be a mapping")
        mode = raw.get("mode")
        selected_on = raw.get("selected_on")
        if mode not in DISPLAY_MODES or not isinstance(selected_on, date):
            raise ConfigError("display mode state is invalid")
        return mode if selected_on == today else TASKBOARD_MODE

    def select(self, mode: str, today: date) -> None:
        if mode not in DISPLAY_MODES:
            raise ValueError(f"unknown display mode: {mode}")
        with _MODE_LOCK:
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
                    yaml.safe_dump(
                        {"mode": mode, "selected_on": today},
                        handle,
                        sort_keys=False,
                    )
                os.replace(temporary_path, self.path)
            except OSError as exc:
                if "temporary_path" in locals():
                    temporary_path.unlink(missing_ok=True)
                raise ConfigError(f"display mode cannot be updated: {self.path}") from exc
