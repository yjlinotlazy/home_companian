from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
import os
from pathlib import Path
import tempfile
from threading import Lock

from .config import ConfigError, ITEM_TYPES, RewardConfig


_COMPLETION_LOCK = Lock()


@dataclass(frozen=True)
class ChecklistItem:
    id: int
    type: str
    text: str


@dataclass(frozen=True)
class ChecklistCompletion:
    date: date
    item_id: int
    points: int
    completed_at: datetime


@dataclass(frozen=True)
class RewardRedemption:
    date: date
    reward_id: str
    cost: int
    redeemed_at: datetime


class ChecklistStore:
    def __init__(self, library_dir: Path) -> None:
        self.items_path = library_dir / "checklists.csv"
        self.completions_path = library_dir / "checklist_completions.csv"
        self.redemptions_path = library_dir / "reward_redemptions.csv"
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
                if reader.fieldnames != ["id", "type", "text"]:
                    raise ConfigError(
                        "checklists.csv columns must be exactly: id,type,text"
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
                    item_type = (row["type"] or "").strip()
                    text = (row["text"] or "").strip()
                    if item_type not in ITEM_TYPES:
                        raise ConfigError(
                            f"checklists.csv line {line}: type must be "
                            "personal or family_task"
                        )
                    if not text:
                        raise ConfigError(f"checklists.csv line {line}: text must not be empty")
                    seen_ids.add(item_id)
                    items.append(ChecklistItem(item_id, item_type, text))
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
                if reader.fieldnames != ["date", "item_id", "points", "completed_at"]:
                    raise ConfigError(
                        "checklist_completions.csv columns must be exactly: "
                        "date,item_id,points,completed_at"
                    )
                rows: list[ChecklistCompletion] = []
                seen: set[tuple[date, int]] = set()
                for row in reader:
                    line = reader.line_num
                    try:
                        completed_date = date.fromisoformat(row["date"])
                        item_id = int(row["item_id"])
                        points = int(row["points"])
                        completed_at = datetime.fromisoformat(row["completed_at"])
                    except (TypeError, ValueError) as exc:
                        raise ConfigError(
                            f"checklist_completions.csv line {line}: invalid value"
                        ) from exc
                    key = (completed_date, item_id)
                    if item_id <= 0 or points <= 0 or key in seen:
                        raise ConfigError(
                            f"checklist_completions.csv line {line}: "
                            "item_id and points must be positive; item_id must be "
                            "unique per date"
                        )
                    seen.add(key)
                    rows.append(
                        ChecklistCompletion(
                            completed_date,
                            item_id,
                            points,
                            completed_at,
                        )
                    )
        except csv.Error as exc:
            raise ConfigError(
                f"invalid CSV in {self.completions_path}: {exc}"
            ) from exc
        return tuple(rows)

    def redemptions(self) -> tuple[RewardRedemption, ...]:
        if not self.redemptions_path.exists():
            return ()
        try:
            handle = self.redemptions_path.open(encoding="utf-8-sig", newline="")
        except OSError as exc:
            raise ConfigError(
                f"reward redemptions file cannot be opened: {self.redemptions_path}"
            ) from exc
        try:
            with handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames != ["date", "reward_id", "cost", "redeemed_at"]:
                    raise ConfigError(
                        "reward_redemptions.csv columns must be exactly: "
                        "date,reward_id,cost,redeemed_at"
                    )
                rows: list[RewardRedemption] = []
                for row in reader:
                    line = reader.line_num
                    try:
                        redeemed_date = date.fromisoformat(row["date"])
                        reward_id = row["reward_id"].strip()
                        cost = int(row["cost"])
                        redeemed_at = datetime.fromisoformat(row["redeemed_at"])
                    except (AttributeError, TypeError, ValueError) as exc:
                        raise ConfigError(
                            f"reward_redemptions.csv line {line}: invalid value"
                        ) from exc
                    if not reward_id or cost <= 0:
                        raise ConfigError(
                            f"reward_redemptions.csv line {line}: "
                            "reward_id and cost must be positive"
                        )
                    rows.append(
                        RewardRedemption(
                            redeemed_date,
                            reward_id,
                            cost,
                            redeemed_at,
                        )
                    )
        except csv.Error as exc:
            raise ConfigError(
                f"invalid CSV in {self.redemptions_path}: {exc}"
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
        item = next((item for item in self.items() if item.id == item_id), None)
        if item is None:
            raise ValueError(f"unknown checklist item: {item_id}")
        with self._lock:
            rows = list(self.completions())
            key = (now.date(), item_id)
            rows = [row for row in rows if (row.date, row.item_id) != key]
            if completed:
                points = 1 if item.type == "personal" else 2
                rows.append(ChecklistCompletion(now.date(), item_id, points, now))
            rows.sort(key=lambda row: (row.date, row.completed_at, row.item_id))
            self._write_completions(rows)

    def reward_score(
        self,
        reward: RewardConfig,
        now: datetime | None = None,
    ) -> int:
        now = (now or datetime.now()).astimezone()
        latest_redemption = max(
            (
                row.redeemed_at
                for row in self.redemptions()
                if row.reward_id == reward.id and row.redeemed_at <= now
            ),
            default=None,
        )
        earned = (reward.initial_points if latest_redemption is None else 0) + sum(
            row.points
            for row in self.completions()
            if row.completed_at <= now
            and (latest_redemption is None or row.completed_at > latest_redemption)
        )
        return min(reward.cost, earned)

    def redeem(
        self,
        reward: RewardConfig,
        now: datetime | None = None,
    ) -> RewardRedemption:
        now = (now or datetime.now()).astimezone()
        with self._lock:
            if self.reward_score(reward, now) < reward.cost:
                raise ValueError(f"not enough points to redeem {reward.name}")
            redemption = RewardRedemption(now.date(), reward.id, reward.cost, now)
            rows = list(self.redemptions())
            rows.append(redemption)
            rows.sort(key=lambda row: row.redeemed_at)
            self._write_redemptions(rows)
            return redemption

    def _write_completions(self, rows: list[ChecklistCompletion]) -> None:
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
                writer.writerow(("date", "item_id", "points", "completed_at"))
                writer.writerows(
                    (
                        row.date.isoformat(),
                        row.item_id,
                        row.points,
                        row.completed_at.isoformat(),
                    )
                    for row in rows
                )
            os.replace(temporary_path, self.completions_path)
        except OSError as exc:
            if "temporary_path" in locals():
                temporary_path.unlink(missing_ok=True)
            raise ConfigError(
                f"checklist completions file cannot be updated: {self.completions_path}"
            ) from exc

    def _write_redemptions(self, rows: list[RewardRedemption]) -> None:
        try:
            self.redemptions_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="",
                dir=self.redemptions_path.parent,
                prefix=f".{self.redemptions_path.name}.",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                writer = csv.writer(handle, lineterminator="\n")
                writer.writerow(("date", "reward_id", "cost", "redeemed_at"))
                writer.writerows(
                    (
                        row.date.isoformat(),
                        row.reward_id,
                        row.cost,
                        row.redeemed_at.isoformat(),
                    )
                    for row in rows
                )
            os.replace(temporary_path, self.redemptions_path)
        except OSError as exc:
            if "temporary_path" in locals():
                temporary_path.unlink(missing_ok=True)
            raise ConfigError(
                f"reward redemptions file cannot be updated: {self.redemptions_path}"
            ) from exc
