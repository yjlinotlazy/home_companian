from __future__ import annotations

from dataclasses import dataclass
@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class Template:
    id: str
    width: int
    height: int
    slots: tuple[tuple[int, Rect], ...]

    def slot(self, slot_id: int) -> Rect:
        for candidate_id, rect in self.slots:
            if candidate_id == slot_id:
                return rect
        raise KeyError(slot_id)


@dataclass(frozen=True)
class SlotAssignment:
    slot_id: int
    module: str
    options: tuple[tuple[str, str], ...] = ()

    def option(self, key: str, default: str | None = None) -> str | None:
        return dict(self.options).get(key, default)


@dataclass(frozen=True)
class PanelConfig:
    template: str
    slots: tuple[SlotAssignment, ...]


@dataclass(frozen=True)
class StatusAssignment:
    module: str
    options: tuple[tuple[str, str], ...] = ()

    def option(self, key: str, default: str | None = None) -> str | None:
        return dict(self.options).get(key, default)


@dataclass(frozen=True)
class StatusBarConfig:
    left: tuple[StatusAssignment, ...] = ()
    center: tuple[StatusAssignment, ...] = ()
    right: tuple[StatusAssignment, ...] = ()
