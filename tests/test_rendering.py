from datetime import datetime
from pathlib import Path
import unittest

from PIL import Image

from home_companian.config import Item
from home_companian.rendering import (
    FRAMEBUFFER_SIZE,
    HEIGHT,
    VISIBLE_WIDTH,
    image_to_framebuffer,
    render_scene,
)


FONT = Path("/usr/share/fonts/adobe-source-han-sans/SourceHanSansCN-Regular.otf")


class FramebufferTests(unittest.TestCase):
    def test_white_image_produces_white_framebuffer(self) -> None:
        framebuffer = image_to_framebuffer(Image.new("1", (VISIBLE_WIDTH, HEIGHT), 1))
        self.assertEqual(len(framebuffer), FRAMEBUFFER_SIZE)
        self.assertEqual(framebuffer, b"\xff" * FRAMEBUFFER_SIZE)

    def test_maps_visible_corners_with_rotation(self) -> None:
        image = Image.new("1", (VISIBLE_WIDTH, HEIGHT), 1)
        image.putpixel((0, 0), 0)
        image.putpixel((791, 271), 0)
        framebuffer = image_to_framebuffer(image)

        self.assertEqual(framebuffer[27199] & 0x01, 0)
        self.assertEqual(framebuffer[0] & 0x80, 0)

    @unittest.skipUnless(FONT.exists(), "Source Han Sans font is not installed")
    def test_rendered_scene_has_panel_dimensions(self) -> None:
        image = render_scene(
            Item("walk", "散步", "出门走一走"),
            FONT,
            battery=82,
            now=datetime(2026, 7, 15, 12, 30),
        )
        self.assertEqual(image.size, (VISIBLE_WIDTH, HEIGHT))
        self.assertEqual(image.mode, "1")


if __name__ == "__main__":
    unittest.main()

