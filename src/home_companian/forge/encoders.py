from __future__ import annotations

from io import BytesIO
from typing import Protocol

from PIL import Image

from ..devices import DeviceProfile


class Encoder(Protocol):
    name: str

    def encode(self, image: Image.Image, profile: DeviceProfile) -> bytes: ...


class PngEncoder:
    name = "png"

    def encode(self, image: Image.Image, profile: DeviceProfile) -> bytes:
        if image.size != (profile.width, profile.height):
            raise ValueError(
                f"image must be {profile.width}x{profile.height}, "
                f"got {image.width}x{image.height}"
            )
        encoded = image.convert("L")
        if 1 < profile.grayscale_levels < 256:
            maximum = profile.grayscale_levels - 1
            encoded = encoded.point(
                lambda pixel: round(round(pixel * maximum / 255) * 255 / maximum)
            )
        output = BytesIO()
        encoded.save(output, format="PNG")
        return output.getvalue()


class CrowPanel1BitEncoder:
    name = "crowpanel_1bit"
    memory_width = 800
    seam_x = 396
    threshold = 180

    def encode(self, image: Image.Image, profile: DeviceProfile) -> bytes:
        if image.size != (profile.width, profile.height):
            raise ValueError(
                f"image must be {profile.width}x{profile.height}, "
                f"got {image.width}x{image.height}"
            )
        framebuffer_size = self.memory_width * profile.height // 8
        monochrome = image.convert("L").point(
            lambda pixel: 255 if pixel > self.threshold else 0
        )
        framebuffer = bytearray([0xFF] * framebuffer_size)
        for visible_y in range(profile.height):
            for visible_x in range(profile.width):
                if monochrome.getpixel((visible_x, visible_y)) != 0:
                    continue
                memory_x = visible_x + (8 if visible_x >= self.seam_x else 0)
                memory_x = self.memory_width - memory_x - 1
                memory_y = profile.height - visible_y - 1
                offset = memory_y * (self.memory_width // 8) + memory_x // 8
                framebuffer[offset] &= ~(0x80 >> (memory_x % 8))
        return bytes(framebuffer)
