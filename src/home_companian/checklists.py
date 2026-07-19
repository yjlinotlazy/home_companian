from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
import os
from pathlib import Path
import tempfile
from threading import Lock

from .config import ConfigError


_COMPLETION_LOCK = Lock()


@dataclass(frozen=True)
class ChecklistItem:
    id: int
    group: str
    text: str


@dataclass(frozen=True)
class ChecklistCompletion:
    date: date
    item_id: int
    completed_at: datetime


class ChecklistStore:
    def __init__(self, library_dir: Path) -> None:
        self.items_path = library_dir / "checklists.csv"
        self.completions_path = library_dir / "checklist_completions.csv"
        self._lock = _COMPLETION_LOCK

    def items(self) -> tuple[ChecklistItem, ...]:
        try:
            handle = self.items_path.open(encoding="utf-8-sig", newline="")
        except OSError as exc:
            raise ConfigError(
                f"checklist items file cannot be opened: {self.items_path}"
            ) from exc
        try:
            with handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames != ["id", "group", "text"]:
                    raise ConfigError(
                        "checklists.csv columns must be exactly: id,group,text"
                    )
                items: list[ChecklistItem] = []
                seen_ids: set[int] = set()
                for row in reader:
                    line = reader.line_num
                    if None in row or any(value is None for value in row.values()):
                        raise ConfigError(
                            f"checklists.csv line {line}: expected exactly 3 columns"
                        )
                    try:
                        item_id = int(row["id"])
                    except (TypeError, ValueError) as exc:
                        raise ConfigError(
                            f"checklists.csv line {line}: id must be a positive integer"
                        ) from exc
                    if item_id <= 0:
                        raise ConfigError(
                            f"checklists.csv line {line}: id must be a positive integer"
                        )
                    if item_id in seen_ids:
                        raise ConfigError(f"duplicate checklist item id: {item_id}")
                    group = (row["group"] or "").strip()
                    text = (row["text"] or "").strip()
                    if not group or not text:
                        raise ConfigError(
                            f"checklists.csv line {line}: group and text must not be empty"
                        )
                    seen_ids.add(item_id)
                    items.append(ChecklistItem(item_id, group, text))
        except csv.Error as exc:
            raise ConfigError(f"invalid CSV in {self.items_path}: {exc}") from exc
        if not items:
            raise ConfigError("checklists.csv must contain at least one item")
        return tuple(items)

    def completions(self) -> tuple[ChecklistCompletion, ...]:
        if not self.completions_path.exists():
            return ()
        try:
            handle = self.completions_path.open(encoding="utf-8-sig", newline="")
        except OSError as exc:
            raise ConfigError(
                f"checklist completions file cannot be opened: {self.completions_path}"
            ) from exc
        try:
            with handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames != ["date", "item_id", "completed_at"]:
                    raise ConfigError(
                        "checklist_completions.csv columns must be exactly: "
                        "date,item_id,completed_at"
                    )
                rows: list[ChecklistCompletion] = []
                seen: set[tuple[date, int]] = set()
                for row in reader:
                    line = reader.line_num
                    try:
                        completed_date = date.fromisoformat(row["date"])
                        item_id = int(row["item_id"])
                        completed_at = datetime.fromisoformat(row["completed_at"])
                    except (TypeError, ValueError) as exc:
                        raise ConfigError(
                            f"checklist_completions.csv line {line}: invalid value"
                        ) from exc
                    key = (completed_date, item_id)
                    if item_id <= 0 or key in seen:
                        raise ConfigError(
                            f"checklist_completions.csv line {line}: "
                            "item_id must be positive and unique per date"
                        )
                    seen.add(key)
                    rows.append(ChecklistCompletion(completed_date, item_id, completed_at))
        except csv.Error as exc:
            raise ConfigError(
                f"invalid CSV in {self.completions_path}: {exc}"
            ) from exc
        return tuple(rows)

    def completed_ids(self, day: date) -> frozenset[int]:
        return frozenset(
            completion.item_id
            for completion in self.completions()
            if completion.date == day
        )

    def set_completed(
        self,
        item_id: int,
        completed: bool,
        now: datetime | None = None,
    ) -> None:
        now = (now or datetime.now()).astimezone()
        if item_id not in {item.id for item in self.items()}:
            raise ValueError(f"unknown checklist item: {item_id}")
        with self._lock:
            rows = list(self.completions())
            key = (now.date(), item_id)
            rows = [row for row in rows if (row.date, row.item_id) != key]
            if completed:
                rows.append(ChecklistCompletion(now.date(), item_id, now))
            rows.sort(key=lambda row: (row.date, row.completed_at, row.item_id))
            self._write(rows)

    def _write(self, rows: list[ChecklistCompletion]) -> None:
        try:
            self.completions_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="",
                dir=self.completions_path.parent,
                prefix=f".{self.completions_path.name}.",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                writer = csv.writer(handle, lineterminator="\n")
                writer.writerow(("date", "item_id", "completed_at"))
                writer.writerows(
                    (row.date.isoformat(), row.item_id, row.completed_at.isoformat())
                    for row in rows
                )
            os.replace(temporary_path, self.completions_path)
        except OSError as exc:
            if "temporary_path" in locals():
                temporary_path.unlink(missing_ok=True)
            raise ConfigError(
                f"checklist completions file cannot be updated: {self.completions_path}"
            ) from exc
