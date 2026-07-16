from __future__ import annotations

from datetime import time
import random
from threading import Lock

from .config import Item, Settings


def _items_by_id(settings: Settings) -> dict[int, Item]:
    return {item.id: item for item in settings.items}


def select_scheduled(settings: Settings, at: time) -> Item:
    if not settings.schedule:
        raise ValueError("schedule is empty")

    selected = settings.schedule[-1]
    for entry in settings.schedule:
        if entry.time > at:
            break
        selected = entry
    return _items_by_id(settings)[selected.item_id]


class RandomSelector:
    def __init__(self) -> None:
        self._last_item_id: int | None = None
        self._lock = Lock()

    def select(self, settings: Settings) -> Item:
        items = _items_by_id(settings)
        with self._lock:
            candidates = [
                item_id
                for item_id in settings.random_items
                if len(settings.random_items) == 1 or item_id != self._last_item_id
            ]
            selected_id = random.choice(candidates)
            self._last_item_id = selected_id
        return items[selected_id]

    def remember(self, item_id: int) -> None:
        with self._lock:
            self._last_item_id = item_id
