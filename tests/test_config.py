from datetime import time
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from home_companian.config import ConfigError, load_config


def resolved_settings(path: Path):
    config = load_config(path)
    return config.for_device(config.default_device)


def device_sections(presentation: str = "") -> str:
    presentation = presentation or (
        "      panel:\n"
        "        template: landscape_1\n"
        "        slots:\n"
        "          1: {module: items}\n"
    )
    return (
        "default_device: wall\n"
        "channels:\n"
        "  home:\n"
        "    mode: scheduled\n"
        "    schedule:\n"
        "      - {time: '12:00', item: 1}\n"
        "    random_items: [1]\n"
        "devices:\n"
        "  wall:\n"
        "    profile: crowpanel_579\n"
        "    channel: home\n"
        "    refresh:\n"
        "      minutes: 60\n"
        "      active_start: '07:00'\n"
        "      active_end: '22:00'\n"
        "    presentation:\n"
        f"{presentation}"
    )


class ConfigTests(unittest.TestCase):
    def test_rejects_legacy_top_level_display_config(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "items.csv").write_text(
                "id,type,text\n1,personal,Walk\n", encoding="utf-8"
            )
            path = root / "config.yaml"
            path.write_text(
                "font: /tmp/font.otf\nlibrary_dir: .\n"
                "mode: random\nrandom_items: [1]\n"
                "schedule:\n  - {time: '12:00', item: 1}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "channels must be a mapping"):
                resolved_settings(path)

    def test_selects_device_specific_refresh_and_presentation(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "items.csv").write_text(
                "id,type,text\n1,personal,Walk\n", encoding="utf-8"
            )
            path = root / "config.yaml"
            second = (
                "  desk:\n"
                "    profile: crowpanel_579\n"
                "    channel: home\n"
                "    refresh:\n"
                "      minutes: 15\n"
                "      active_start: '08:00'\n"
                "      active_end: '20:00'\n"
                "    presentation:\n"
                "      panel:\n"
                "        template: landscape_2\n"
                "        slots:\n"
                "          1: {module: items}\n"
            )
            path.write_text(
                "font: /tmp/font.otf\nlibrary_dir: .\n"
                + device_sections()
                + second,
                encoding="utf-8",
            )
            configured = load_config(path).for_device("desk")

        self.assertEqual(configured.device_id, "desk")
        self.assertEqual(configured.refresh_minutes, 15)
        self.assertEqual(configured.active_start.hour, 8)
        self.assertEqual(configured.panel.template, "landscape_2")

    def test_loads_daily_variable_refresh_schedule(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "items.csv").write_text(
                "id,type,text\n1,personal,Walk\n", encoding="utf-8"
            )
            path = root / "config.yaml"
            content = device_sections().replace(
                "      minutes: 60\n"
                "      active_start: '07:00'\n"
                "      active_end: '22:00'\n",
                "      schedule:\n"
                "        - {start: '08:00', end: '12:00', minutes: 30}\n"
                "        - {start: '12:00', end: '18:00', minutes: 90}\n"
                "        - {start: '18:00', end: '20:00', minutes: 30}\n",
            )
            path.write_text(
                "font: /tmp/font.otf\nlibrary_dir: .\n" + content,
                encoding="utf-8",
            )

            configured = resolved_settings(path)

        self.assertEqual(configured.active_start, time(8, 0))
        self.assertEqual(configured.active_end, time(20, 0))
        self.assertEqual(
            [period.minutes for period in configured.refresh_periods],
            [30, 90, 30],
        )

    def test_loads_minimal_config(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "config.yaml"
            (root / "items.csv").write_text(
                "id,type,text\n1,personal,Walk\n", encoding="utf-8"
            )
            path.write_text(
                "font: /tmp/font.otf\nlibrary_dir: .\n"
                + device_sections(),
                encoding="utf-8",
            )
            settings = resolved_settings(path)

        self.assertEqual(settings.items[0].id, 1)
        self.assertEqual(settings.items[0].type, "personal")
        self.assertEqual(settings.items[0].text, "Walk")
        self.assertEqual(settings.mode, "scheduled")
        self.assertEqual(settings.status_bar.center[0].module, "solar_term")
        self.assertEqual(settings.status_bar.right[0].module, "weekday")
        self.assertEqual(
            (
                settings.reward.id,
                settings.reward.name,
                settings.reward.cost,
                settings.reward.initial_points,
            ),
            ("toy", "玩具", 50, 25),
        )

    def test_loads_reward_setting(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "items.csv").write_text(
                "id,type,text\n1,personal,Walk\n", encoding="utf-8"
            )
            path = root / "config.yaml"
            path.write_text(
                "font: /tmp/font.otf\nlibrary_dir: .\n"
                "reward: {id: book, name: 书, cost: 20, initial_points: 5}\n"
                + device_sections(),
                encoding="utf-8",
            )

            configured = resolved_settings(path)

        self.assertEqual(
            (
                configured.reward.id,
                configured.reward.name,
                configured.reward.cost,
                configured.reward.initial_points,
            ),
            ("book", "书", 20, 5),
        )

    def test_loads_checklist_membership_and_order(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "items.csv").write_text(
                "id,type,text\n1,personal,Walk\n", encoding="utf-8"
            )
            path = root / "config.yaml"
            path.write_text(
                "font: /tmp/font.otf\nlibrary_dir: .\n"
                "checklists:\n"
                "  person_1: [3, 1, 2]\n"
                "  family:\n"
                "    items: [4, 5, 6]\n"
                "    daily_limit: 2\n"
                + device_sections(),
                encoding="utf-8",
            )

            configured = resolved_settings(path)

        self.assertEqual(
            [
                (group.id, group.item_ids, group.daily_limit)
                for group in configured.checklist_groups
            ],
            [("person_1", (3, 1, 2), None), ("family", (4, 5, 6), 2)],
        )

    def test_loads_status_bar_modules(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "config.yaml"
            (root / "items.csv").write_text(
                "id,type,text\n1,personal,Walk\n", encoding="utf-8"
            )
            path.write_text(
                "font: /tmp/font.otf\nlibrary_dir: .\n"
                + device_sections(
                    "      status_bar:\n"
                    "        left: []\n"
                    "        center:\n"
                    "          - {module: solar_term}\n"
                    "        right:\n"
                    "          - {module: time, format: '%H:%M'}\n"
                    "      panel:\n"
                    "        template: landscape_1\n"
                    "        slots:\n"
                    "          1: {module: items}\n"
                ),
                encoding="utf-8",
            )
            configured = resolved_settings(path)

        self.assertEqual(configured.status_bar.left, ())
        self.assertEqual(configured.status_bar.center[0].module, "solar_term")
        self.assertEqual(configured.status_bar.right[0].option("format"), "%H:%M")

    def test_loads_font_candidates(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "items.csv").write_text(
                "id,type,text\n1,personal,Walk\n", encoding="utf-8"
            )
            path = root / "config.yaml"
            path.write_text(
                "font: /tmp/medium.ttf\n"
                "fonts:\n  文楷: /tmp/medium.ttf\n  黑体: /tmp/sans.otf\n"
                "library_dir: .\n"
                + device_sections(),
                encoding="utf-8",
            )
            settings = resolved_settings(path)

        self.assertEqual([choice.name for choice in settings.fonts], ["文楷", "黑体"])

    def test_loads_panel_assignment(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "items.csv").write_text(
                "id,type,text\n1,personal,Walk\n", encoding="utf-8"
            )
            path = root / "config.yaml"
            path.write_text(
                "font: /tmp/font.otf\nlibrary_dir: .\n"
                + device_sections(
                    "      panel:\n"
                    "        template: landscape_1\n"
                    "        slots:\n"
                    "          1: {module: items, mode: random}\n"
                ),
                encoding="utf-8",
            )
            settings = resolved_settings(path)

        self.assertEqual(settings.panel.template, "landscape_1")
        self.assertEqual(settings.panel.slots[0].module, "items")
        self.assertEqual(settings.panel.slots[0].option("mode"), "random")

    def test_loads_presentation_panel_rotation(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "items.csv").write_text(
                "id,type,text\n1,personal,Walk\n", encoding="utf-8"
            )
            path = root / "config.yaml"
            path.write_text(
                "font: /tmp/font.otf\nlibrary_dir: .\n"
                + device_sections(
                    "      panels:\n"
                    "        - template: landscape_1\n"
                    "          slots:\n"
                    "            1: {module: items}\n"
                    "        - template: landscape_1\n"
                    "          slots:\n"
                    "            1: {module: math, type: game24}\n"
                ),
                encoding="utf-8",
            )

            settings = resolved_settings(path)

        self.assertEqual(len(settings.panels), 2)
        self.assertEqual(settings.panels[1].slots[0].module, "math")
        self.assertEqual(settings.panels[1].slots[0].option("type"), "game24")

    def test_rejects_selected_font_outside_candidates(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "items.csv").write_text(
                "id,type,text\n1,personal,Walk\n", encoding="utf-8"
            )
            path = root / "config.yaml"
            path.write_text(
                "font: /tmp/other.ttf\nfonts:\n  文楷: /tmp/medium.ttf\n"
                "library_dir: .\n"
                "schedule:\n  - {time: '12:00', item: 1}\n"
                "random_items: [1]\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "must match"):
                resolved_settings(path)

    def test_rejects_duplicate_ids(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "config.yaml"
            (root / "items.csv").write_text(
                "id,type,text\n1,personal,Walk\n1,family_task,Again\n",
                encoding="utf-8",
            )
            path.write_text(
                "font: /tmp/font.otf\nlibrary_dir: .\n"
                "schedule:\n  - {time: '12:00', item: 1}\n"
                "random_items: [1]\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "duplicate item id"):
                resolved_settings(path)

    def test_rejects_wrong_csv_columns(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "items.csv").write_text(
                "id,type,title,text\n1,personal,Walk,Outside\n", encoding="utf-8"
            )
            path = root / "config.yaml"
            path.write_text(
                "font: /tmp/font.otf\nlibrary_dir: .\n"
                "schedule:\n  - {time: '12:00', item: 1}\n"
                "random_items: [1]\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "columns must be exactly"):
                resolved_settings(path)

    def test_rejects_unknown_item_type(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "items.csv").write_text(
                "id,type,text\n1,other,Walk\n", encoding="utf-8"
            )
            path = root / "config.yaml"
            path.write_text(
                "font: /tmp/font.otf\nlibrary_dir: .\n"
                "schedule:\n  - {time: '12:00', item: 1}\n"
                "random_items: [1]\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "personal or family_task"):
                resolved_settings(path)


if __name__ == "__main__":
    unittest.main()
