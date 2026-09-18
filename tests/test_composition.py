from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image, ImageDraw

from home_companian.devices import CROWPANEL_579, KINDLE_6_167PPI
from home_companian.forge.composition import _add_kindle_decorations


class KindleDecorationTests(unittest.TestCase):
    def test_adds_small_corner_decorations_to_kindle(self) -> None:
        with TemporaryDirectory() as temporary_dir:
            decoration_dir = Path(temporary_dir) / "decorations"
            decoration_dir.mkdir()
            for filename in ("rainbow.png", "heart_completed.png"):
                source = Image.new("L", (100, 100), 255)
                ImageDraw.Draw(source).rectangle((10, 10, 90, 90), fill=0)
                source.save(decoration_dir / filename)

            image = Image.new("L", (600, 800), 255)
            _add_kindle_decorations(image, Path(temporary_dir), KINDLE_6_167PPI)

            self.assertLess(image.getpixel((470, 20)), 255)
            self.assertLess(image.getpixel((560, 760)), 255)
            self.assertEqual(image.getpixel((300, 400)), 255)

    def test_does_not_decorate_non_kindle_profiles(self) -> None:
        image = Image.new("1", (792, 272), 1)

        _add_kindle_decorations(image, Path("missing"), CROWPANEL_579)

        self.assertEqual(image.getbbox(), (0, 0, 792, 272))


if __name__ == "__main__":
    unittest.main()
