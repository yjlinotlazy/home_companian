from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from home_companian.config import ConfigError, load_settings


class ConfigTests(unittest.TestCase):
    def test_loads_minimal_config(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text(
                "font: /tmp/font.otf\nitems:\n  - id: walk\n    title: Walk\n",
                encoding="utf-8",
            )
            settings = load_settings(path)

        self.assertEqual(settings.items[0].id, "walk")
        self.assertEqual(settings.mode, "scheduled")

    def test_rejects_duplicate_ids(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text(
                "font: /tmp/font.otf\nitems:\n"
                "  - {id: walk, title: Walk}\n"
                "  - {id: walk, title: Again}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "duplicate item id"):
                load_settings(path)


if __name__ == "__main__":
    unittest.main()

