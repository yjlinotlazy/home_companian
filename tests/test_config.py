from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from home_companian.config import ConfigError, load_settings


class ConfigTests(unittest.TestCase):
    def test_loads_minimal_config(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "config.yaml"
            (root / "items.csv").write_text(
                "id,type,text\n1,personal,Walk\n", encoding="utf-8"
            )
            path.write_text(
                "font: /tmp/font.otf\nlibrary_dir: .\n"
                "schedule:\n  - {time: '12:00', item: 1}\n"
                "random_items: [1]\n",
                encoding="utf-8",
            )
            settings = load_settings(path)

        self.assertEqual(settings.items[0].id, 1)
        self.assertEqual(settings.items[0].type, "personal")
        self.assertEqual(settings.items[0].text, "Walk")
        self.assertEqual(settings.mode, "scheduled")
        self.assertEqual(settings.status_bar.center[0].module, "solar_term")
        self.assertEqual(settings.status_bar.right[0].module, "weekday")

    def test_loads_status_bar_modules(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "config.yaml"
            (root / "items.csv").write_text(
                "id,type,text\n1,personal,Walk\n", encoding="utf-8"
            )
            path.write_text(
                "font: /tmp/font.otf\nlibrary_dir: .\n"
                "status_bar:\n  left: []\n  center:\n    - {module: solar_term}\n"
                "  right:\n    - {module: time, format: '%H:%M'}\n"
                "schedule:\n  - {time: '12:00', item: 1}\n"
                "random_items: [1]\n",
                encoding="utf-8",
            )
            configured = load_settings(path)

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
                "schedule:\n  - {time: '12:00', item: 1}\n"
                "random_items: [1]\n",
                encoding="utf-8",
            )
            settings = load_settings(path)

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
                "panel:\n  template: landscape_1\n"
                "  slots:\n    1: {module: items, mode: random}\n"
                "schedule:\n  - {time: '12:00', item: 1}\n"
                "random_items: [1]\n",
                encoding="utf-8",
            )
            settings = load_settings(path)

        self.assertEqual(settings.panel.template, "landscape_1")
        self.assertEqual(settings.panel.slots[0].module, "items")
        self.assertEqual(settings.panel.slots[0].option("mode"), "random")

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
                load_settings(path)

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
                load_settings(path)

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
                load_settings(path)

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
                load_settings(path)


if __name__ == "__main__":
    unittest.main()
