from datetime import datetime
import unittest

from PIL import Image

from home_companian.devices import (
    CROWPANEL_579,
    KINDLE_6_212PPI,
    get_device_profile,
)
from home_companian.domain import PanelConfig, SlotAssignment
from home_companian.forge.encoders import CrowPanel1BitEncoder, PngEncoder
from home_companian.forge.engine import Forge
from home_companian.forge.models import Presentation, Scene, SceneFragment


class ForgeTests(unittest.TestCase):
    def test_scene_id_is_stable_and_device_independent(self) -> None:
        fragments = (SceneFragment("task", "items", 3, "task"),)
        first = Scene.create(fragments, datetime(2026, 7, 17, 12))
        second = Scene.create(fragments, datetime(2026, 7, 17, 12))

        self.assertEqual(first.id, second.id)
        self.assertNotIn("crowpanel", first.id)

    def test_presentation_maps_fragments_to_slots(self) -> None:
        presentation = Presentation.from_panel(
            PanelConfig(
                "landscape_2",
                (SlotAssignment(1, "items"), SlotAssignment(2, "chinese")),
            )
        )
        self.assertEqual(
            [(placement.slot_id, placement.fragment_id) for placement in presentation.placements],
            [(1, "fragment-0"), (2, "fragment-1")],
        )

    def test_crowpanel_encoder_is_profile_specific(self) -> None:
        image = Image.new("1", (CROWPANEL_579.width, CROWPANEL_579.height), 1)
        payload = CrowPanel1BitEncoder().encode(image, CROWPANEL_579)
        self.assertEqual(len(payload), 27_200)
        self.assertEqual(payload, b"\xff" * 27_200)

    def test_crowpanel_encoder_maps_visible_corners_with_rotation(self) -> None:
        image = Image.new("1", (CROWPANEL_579.width, CROWPANEL_579.height), 1)
        image.putpixel((0, 0), 0)
        image.putpixel((791, 271), 0)
        payload = CrowPanel1BitEncoder().encode(image, CROWPANEL_579)

        self.assertEqual(payload[27199] & 0x01, 0)
        self.assertEqual(payload[0] & 0x80, 0)

    def test_png_encoder_and_frame_identity(self) -> None:
        profile = type(CROWPANEL_579)(
            "test_png", 20, 10, 0, "png", "image/png"
        )
        image = Image.new("L", (20, 10), 255)
        payload = PngEncoder().encode(image, profile)
        first = Forge().encode(image, "scene-1", profile, datetime(2026, 7, 17))
        second = Forge().encode(image, "scene-1", profile, datetime(2026, 7, 18))

        self.assertTrue(payload.startswith(b"\x89PNG"))
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.mime_type, "image/png")

    def test_rejects_unknown_profile(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown device profile"):
            get_device_profile("missing")

    def test_kindle_profile_matches_hardware(self) -> None:
        self.assertEqual((KINDLE_6_212PPI.width, KINDLE_6_212PPI.height), (758, 1024))
        self.assertEqual(KINDLE_6_212PPI.ppi, 212)
        self.assertEqual(KINDLE_6_212PPI.grayscale_levels, 16)
        self.assertEqual(KINDLE_6_212PPI.mime_type, "image/png")


if __name__ == "__main__":
    unittest.main()
