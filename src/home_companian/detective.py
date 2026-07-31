from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tempfile
from threading import Lock
from typing import Any

import yaml

from .config import ConfigError


DEFAULT_HINT_COUNT = 6
MAX_HINT_COUNT = 24
MAX_TITLE_LENGTH = 100
MAX_BODY_LENGTH = 1200
MAX_HINT_LENGTH = 300
_STORE_LOCK = Lock()


@dataclass(frozen=True)
class DetectivePuzzle:
    title: str
    mystery: str
    answer: str
    hints: tuple[str, ...]
    visible: tuple[bool, ...]


class DetectiveStore:
    def __init__(self, library_dir: Path) -> None:
        self.root = library_dir / "detective"
        self.current_path = self.root / "current.yaml"

    def load(self) -> DetectivePuzzle:
        if not self.current_path.exists():
            return DetectivePuzzle(
                "",
                "",
                "",
                ("",) * DEFAULT_HINT_COUNT,
                (False,) * DEFAULT_HINT_COUNT,
            )
        try:
            raw = yaml.safe_load(self.current_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigError(
                f"detective state cannot be opened: {self.current_path}"
            ) from exc
        if not isinstance(raw, dict):
            raise ConfigError("detective/current.yaml must be a mapping")
        try:
            return self._validate(
                raw.get("title"),
                raw.get("mystery"),
                raw.get("answer"),
                raw.get("hints"),
                raw.get("visible"),
            )
        except ValueError as exc:
            raise ConfigError(f"invalid detective state: {exc}") from exc

    def save(
        self,
        title: object,
        mystery: object,
        answer: object,
        hints: object,
        visible: object = None,
    ) -> DetectivePuzzle:
        puzzle = self._validate(title, mystery, answer, hints, visible)
        payload = {
            "title": puzzle.title,
            "mystery": puzzle.mystery,
            "answer": puzzle.answer,
            "hints": list(puzzle.hints),
            "visible": list(puzzle.visible),
        }
        with _STORE_LOCK:
            temporary_path: Path | None = None
            try:
                self.root.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    "w",
                    encoding="utf-8",
                    dir=self.root,
                    prefix=".current.",
                    suffix=".yaml",
                    delete=False,
                ) as handle:
                    temporary_path = Path(handle.name)
                    yaml.safe_dump(
                        payload,
                        handle,
                        allow_unicode=True,
                        sort_keys=False,
                    )
                os.replace(temporary_path, self.current_path)
            except OSError as exc:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
                raise ConfigError(
                    f"detective state cannot be updated: {self.current_path}"
                ) from exc
        return puzzle

    @staticmethod
    def _validate(
        title: object,
        mystery: object,
        answer: object,
        hints: Any,
        visible: Any = None,
    ) -> DetectivePuzzle:
        if not isinstance(title, str):
            raise ValueError("detective title must be text")
        if not isinstance(mystery, str) or not isinstance(answer, str):
            raise ValueError("detective mystery and answer must be text")
        if (
            not isinstance(hints, list)
            or not 1 <= len(hints) <= MAX_HINT_COUNT
            or not all(isinstance(hint, str) for hint in hints)
        ):
            raise ValueError(
                f"detective hints must contain 1 to {MAX_HINT_COUNT} text entries"
            )
        title = title.strip()
        mystery = mystery.strip()
        answer = answer.strip()
        normalized_hints = tuple(hint.strip() for hint in hints)
        if visible is None:
            normalized_visible = (False,) * len(normalized_hints)
        elif (
            not isinstance(visible, list)
            or len(visible) != len(normalized_hints)
            or not all(type(value) is bool for value in visible)
        ):
            raise ValueError("detective visible must contain one boolean per hint")
        else:
            normalized_visible = tuple(visible)
        if len(title) > MAX_TITLE_LENGTH:
            raise ValueError(
                f"detective title must be at most {MAX_TITLE_LENGTH} characters"
            )
        if len(mystery) > MAX_BODY_LENGTH or len(answer) > MAX_BODY_LENGTH:
            raise ValueError(
                f"detective mystery and answer must be at most {MAX_BODY_LENGTH} characters"
            )
        if any(len(hint) > MAX_HINT_LENGTH for hint in normalized_hints):
            raise ValueError(
                f"each detective hint must be at most {MAX_HINT_LENGTH} characters"
            )
        return DetectivePuzzle(
            title,
            mystery,
            answer,
            normalized_hints,
            normalized_visible,
        )
