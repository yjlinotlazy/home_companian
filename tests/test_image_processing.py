from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from home_companian.image_processing import process_file, process_image


class ImageProcessingTests(unittest.TestCase):
    def test_cover_produces_exact_one_bit_size(self) -> None:
        source = Image.new("RGB", (400, 400), "gray")
        processed = process_image(source, size=(200, 100))
        self.assertEqual(processed.size, (200, 100))
        self.assertEqual(processed.mode, "1")

    def test_contain_uses_white_letterbox(self) -> None:
        source = Image.new("L", (100, 100), 0)
        processed = process_image(
            source,
            size=(200, 100),
            fit="contain",
            binarize="threshold",
        )
        self.assertEqual(processed.getpixel((0, 50)), 255)
        self.assertEqual(processed.getpixel((100, 50)), 0)

    def test_threshold_and_invert_are_deterministic(self) -> None:
        source = Image.new("L", (2, 1))
        source.putdata([100, 220])
        processed = process_image(
            source,
            size=(2, 1),
            binarize="threshold",
            threshold=128,
            invert=True,
        )
        self.assertEqual(
            [processed.getpixel((x, 0)) for x in range(2)],
            [255, 0],
        )

    def test_transparent_pixels_become_white(self) -> None:
        source = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        processed = process_image(
            source, size=(1, 1), binarize="threshold"
        )
        self.assertEqual(processed.getpixel((0, 0)), 255)

    def test_trim_removes_input_border(self) -> None:
        source = Image.new("L", (10, 10), 255)
        for coordinate in range(10):
            source.putpixel((coordinate, 0), 0)
            source.putpixel((coordinate, 9), 0)
            source.putpixel((0, coordinate), 0)
            source.putpixel((9, coordinate), 0)
        processed = process_image(
            source,
            size=(8, 8),
            fit="contain",
            binarize="threshold",
            trim=1,
        )
        self.assertEqual(processed.getextrema(), (255, 255))

    def test_content_scale_adds_white_space(self) -> None:
        processed = process_image(
            Image.new("L", (10, 10), 0),
            size=(100, 100),
            fit="contain",
            binarize="threshold",
            content_scale=0.5,
        )
        self.assertEqual(processed.getpixel((0, 0)), 255)
        self.assertEqual(processed.getpixel((50, 50)), 0)

    def test_process_file_writes_one_bit_png(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jpg"
            output = root / "nested" / "output.png"
            Image.new("RGB", (20, 10), "black").save(source)
            process_file(source, output, size=(10, 5))
            with Image.open(output) as written:
                self.assertEqual(written.size, (10, 5))
                self.assertEqual(written.mode, "1")


if __name__ == "__main__":
    unittest.main()
