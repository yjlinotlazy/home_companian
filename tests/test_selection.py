from datetime import time
from pathlib import Path
import unittest

from home_companian.config import FontChoice, Item, ScheduleEntry, Settings
from home_companian.domain import PanelConfig, SlotAssignment, StatusBarConfig
from home_companian.selection import RandomSelector, select_scheduled


def settings(mode: str = "scheduled") -> Settings:
    return Settings(
        device_id="wall",
        profile_id="crowpanel_579",
        channel_id="home",
        mode=mode,
        font=Path("/tmp/font.otf"),
        fonts=(FontChoice("默认", Path("/tmp/font.otf")),),
        latin_font=Path("/tmp/latin.ttf"),
        latin_fonts=(FontChoice("Latin", Path("/tmp/latin.ttf")),),
        library_dir=Path("/tmp/library"),
        refresh_minutes=60,
        active_start=time(7),
        active_end=time(22),
        items=(Item(1, "personal", "Walk"), Item(2, "personal", "Read")),
        schedule=(ScheduleEntry(time(12), 1), ScheduleEntry(time(13), 2)),
        random_items=(1, 2),
        panel=PanelConfig("landscape_1", (SlotAssignment(1, "items"),)),
        status_bar=StatusBarConfig(),
    )


class SelectionTests(unittest.TestCase):
    def test_scheduled_selects_latest_started_item(self) -> None:
        configured = settings()
        self.assertEqual(select_scheduled(configured, time(12, 40)).id, 1)
        self.assertEqual(select_scheduled(configured, time(13, 0)).id, 2)

    def test_scheduled_wraps_to_previous_days_last_item(self) -> None:
        self.assertEqual(select_scheduled(settings(), time(8)).id, 2)

    def test_random_does_not_repeat_with_multiple_items(self) -> None:
        selector = RandomSelector()
        first = selector.select(settings("random"))
        second = selector.select(settings("random"))
        self.assertNotEqual(first.id, second.id)


if __name__ == "__main__":
    unittest.main()
