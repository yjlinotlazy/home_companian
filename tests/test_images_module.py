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
        self.settings = SimpleNamespace(
            library_dir=self.library,
            profile_id="crowpanel_579",
        )
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

    def test_random_selection_can_span_multiple_collections(self) -> None:
        animals = self.library / "images" / "animals"
        animals.mkdir()
        Image.new("1", (200, 200), 255).save(animals / "cat.png")
        assignment = SlotAssignment(
            1, "images", (("collections", "plants,animals"),)
        )
        module = ImagesModule()
        with patch(
            "home_companian.modules.images.random.choice",
            side_effect=lambda values: values[-1],
        ):
            first = module.prepare(self.settings, datetime.now(), assignment)
            second = module.prepare(self.settings, datetime.now(), assignment)
        self.assertEqual((first, second), ("animals/cat.png", "plants/b.png"))

    def test_wildcard_scans_all_image_collection_directories(self) -> None:
        animals = self.library / "images" / "animals"
        animals.mkdir()
        Image.new("1", (200, 200), 255).save(animals / "cat.png")
        raw = self.library / "images" / "raw"
        raw.mkdir()
        Image.new("1", (200, 200), 255).save(raw / "source.png")
        (self.library / "images" / "empty").mkdir()
        assignment = SlotAssignment(
            1, "images", (("collections", "*"),)
        )
        module = ImagesModule()
        with patch(
            "home_companian.modules.images.random.choice",
            side_effect=lambda values: values[0],
        ) as choice:
            module.prepare(self.settings, datetime.now(), assignment)

        self.assertEqual(
            set(choice.call_args.args[0]),
            {"animals/cat.png", "plants/a.png", "plants/b.png"},
        )

    def test_renders_preprocessed_asset_without_resizing(self) -> None:
        image = ImagesModule().render(
            self.settings,
            "plants/a.png",
            Rect(0, 0, 200, 200),
            datetime.now(),
        )
        self.assertEqual((image.size, image.mode), ((200, 200), "L"))

    def test_resizes_grayscale_master_to_slot_at_runtime(self) -> None:
        Image.new("L", (400, 100), 0).save(self.collection / "wide.png")
        rendered = ImagesModule().render(
            self.settings,
            "plants/wide.png",
            Rect(0, 0, 100, 100),
            datetime.now(),
        )
        self.assertEqual((rendered.size, rendered.mode), ((100, 100), "L"))
        self.assertEqual(rendered.getpixel((50, 0)), 255)
        self.assertEqual(rendered.getpixel((50, 50)), 0)

    def test_directory_frame_wraps_contained_image_tightly(self) -> None:
        directory = self.library / "family_album"
        directory.mkdir()
        Image.new("L", (400, 100), 255).save(directory / "wide.png")
        assignment = SlotAssignment(
            1,
            "images",
            (("directory", str(directory)), ("frame", "true")),
        )
        module = ImagesModule()
        content_id = module.prepare(self.settings, datetime.now(), assignment)

        rendered = module.render(
            self.settings,
            content_id,
            Rect(0, 0, 100, 100),
            datetime.now(),
        )

        self.assertEqual(rendered.getpixel((50, 36)), 255)
        self.assertEqual(rendered.getpixel((50, 37)), 96)
        self.assertEqual(rendered.getpixel((0, 49)), 96)
        self.assertEqual(rendered.getpixel((50, 0)), 255)

    def test_kindle_prefers_grey_sibling_regardless_of_extension(self) -> None:
        Image.new("L", (200, 200), 0).save(self.collection / "a_grey.jpg")
        settings = SimpleNamespace(
            library_dir=self.library,
            profile_id="kindle_6_167ppi",
        )

        rendered = ImagesModule().render(
            settings,
            "plants/a.png",
            Rect(0, 0, 200, 200),
            datetime.now(),
        )

        self.assertEqual(rendered.getextrema(), (0, 0))

    def test_kindle_keeps_selected_grey_asset(self) -> None:
        Image.new("L", (200, 200), 0).save(self.collection / "a_grey.png")
        settings = SimpleNamespace(
            library_dir=self.library,
            profile_id="kindle_6_167ppi",
        )

        rendered = ImagesModule().render(
            settings,
            "plants/a_grey.png",
            Rect(0, 0, 200, 200),
            datetime.now(),
        )

        self.assertEqual(rendered.getextrema(), (0, 0))

    def test_kindle_uses_original_when_grey_sibling_is_missing(self) -> None:
        settings = SimpleNamespace(
            library_dir=self.library,
            profile_id="kindle_6_167ppi_landscape",
        )

        rendered = ImagesModule().render(
            settings,
            "plants/a.png",
            Rect(0, 0, 200, 200),
            datetime.now(),
        )

        self.assertEqual(rendered.getextrema(), (255, 255))

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
