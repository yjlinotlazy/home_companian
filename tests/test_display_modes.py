from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from home_companian.display_modes import (
    TASKBOARD_MODE,
    TREASURE_HUNT_MODE,
    DisplayModeStore,
)
from home_companian.service import DisplayService


FONT = "/usr/share/fonts/adobe-source-han-sans/SourceHanSansCN-Regular.otf"


class DisplayModeStoreTests(unittest.TestCase):
    def test_defaults_to_taskboard_and_resets_on_next_day(self) -> None:
        with TemporaryDirectory() as directory:
            store = DisplayModeStore(Path(directory) / "mode.yaml")
            first_day = date(2026, 7, 22)

            self.assertEqual(store.selected(first_day), TASKBOARD_MODE)
            store.select(TREASURE_HUNT_MODE, first_day)
            self.assertEqual(store.selected(first_day), TREASURE_HUNT_MODE)
            self.assertEqual(store.selected(date(2026, 7, 23)), TASKBOARD_MODE)


@unittest.skipUnless(Path(FONT).exists(), "Source Han Sans font is not installed")
class KindleDisplayModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        (root / "items.csv").write_text(
            "id,type,text\n1,personal,Task board\n",
            encoding="utf-8",
        )
        background_dir = root / "treasure_hunt" / "background"
        background_dir.mkdir(parents=True)
        Image.new("L", (300, 320), 255).save(background_dir / "background1.png")
        Image.new("RGBA", (100, 80), (160, 160, 160, 128)).save(
            root / "treasure_hunt" / "check_grey.png"
        )
        (background_dir / "background1.yaml").write_text(
            "text_boxes:\n"
            "  - [0.05, 0.05, 0.4, 0.25]\n"
            "  - [0.55, 0.05, 0.4, 0.25]\n"
            "  - [0.05, 0.375, 0.4, 0.25]\n"
            "  - [0.55, 0.375, 0.4, 0.25]\n"
            "  - [0.05, 0.7, 0.4, 0.25]\n"
            "  - [0.55, 0.7, 0.4, 0.25]\n",
            encoding="utf-8",
        )
        (root / "treasure_hunt" / "current.yaml").write_text(
            "background: background1.png\n"
            "texts: [one, two, three, four, five, six]\n",
            encoding="utf-8",
        )
        config_path = root / "config.yaml"
        config_path.write_text(
            f"font: {FONT}\n"
            "library_dir: .\n"
            "default_device: kindle\n"
            "channels:\n"
            "  home:\n"
            "    mode: random\n"
            "    schedule:\n"
            "      - {time: '12:00', item: 1}\n"
            "    random_items: [1]\n"
            "devices:\n"
            "  kindle:\n"
            "    profile: kindle_6_167ppi_landscape\n"
            "    channel: home\n"
            "    refresh:\n"
            "      minutes: 30\n"
            "      active_start: '07:00'\n"
            "      active_end: '22:00'\n"
            "    presentation:\n"
            "      panel:\n"
            "        template: landscape_4\n"
            "        slots:\n"
            "          1: {module: items}\n",
            encoding="utf-8",
        )
        self.service = DisplayService(config_path, root / "current-kindle.png")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_treasure_hunt_stays_portrait_for_day_then_resets(self) -> None:
        selected_at = datetime(2026, 7, 22, 10, 0)

        selected = self.service.select_display_mode(
            TREASURE_HUNT_MODE,
            selected_at,
        )
        same_day = self.service.deliver(datetime(2026, 7, 22, 18, 0))
        next_day_preview = self.service.preview_next_delivery(
            datetime(2026, 7, 23, 7, 0)
        )
        next_day = self.service.deliver(datetime(2026, 7, 23, 7, 0))

        self.assertEqual(selected.frame.profile_id, "kindle_6_167ppi")
        self.assertEqual(selected.image.size, (600, 800))
        self.assertEqual(same_day.frame.profile_id, "kindle_6_167ppi")
        self.assertEqual(
            next_day_preview.frame.profile_id,
            "kindle_6_167ppi_landscape",
        )
        self.assertEqual(next_day.frame.profile_id, "kindle_6_167ppi_landscape")
        self.assertEqual(next_day.image.size, (800, 600))

    def test_manual_taskboard_switch_replaces_pending_portrait_frame(self) -> None:
        now = datetime(2026, 7, 22, 10, 0)
        self.service.select_display_mode(TREASURE_HUNT_MODE, now)

        taskboard = self.service.select_display_mode(TASKBOARD_MODE, now)

        self.assertEqual(taskboard.frame.profile_id, "kindle_6_167ppi_landscape")
        self.assertEqual(self.service.deliver(now).frame.id, taskboard.frame.id)


if __name__ == "__main__":
    unittest.main()
