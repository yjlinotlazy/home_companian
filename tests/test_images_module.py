from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

from home_companian.config import ConfigError
from home_companian.domain import Rect, SlotAssignment
from home_companian.modules.images import ImagesModule


class ImagesModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.library = Path(self.temporary_directory.name)
        self.collection = self.library / "images" / "plants"
        self.collection.mkdir(parents=True)
        Image.new("1", (200, 200), 255).save(self.collection / "a.png")
        Image.new("1", (200, 200), 0).save(self.collection / "b.png")
        self.settings = SimpleNamespace(library_dir=self.library)
        self.assignment = SlotAssignment(
            1, "images", (("collection", "plants"),)
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_random_selection_avoids_immediate_repeat(self) -> None:
        module = ImagesModule()
        with patch(
            "home_companian.modules.images.random.choice",
            side_effect=lambda values: values[0],
        ):
            first = module.prepare(self.settings, datetime.now(), self.assignment)
            second = module.prepare(self.settings, datetime.now(), self.assignment)
        self.assertEqual((first, second), ("plants/a.png", "plants/b.png"))

    def test_renders_preprocessed_asset_without_resizing(self) -> None:
        image = ImagesModule().render(
            self.settings,
            "plants/a.png",
            Rect(0, 0, 200, 200),
            datetime.now(),
        )
        self.assertEqual((image.size, image.mode), ((200, 200), "1"))

    def test_rejects_asset_with_wrong_dimensions(self) -> None:
        with self.assertRaisesRegex(ConfigError, "must be 100x100"):
            ImagesModule().render(
                self.settings,
                "plants/a.png",
                Rect(0, 0, 100, 100),
                datetime.now(),
            )

    def test_rejects_path_traversal(self) -> None:
        with self.assertRaisesRegex(ConfigError, "invalid image content id"):
            ImagesModule().render(
                self.settings,
                "../a.png",
                Rect(0, 0, 200, 200),
                datetime.now(),
            )


if __name__ == "__main__":
    unittest.main()
