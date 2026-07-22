import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont

from home_companian.config import ConfigError
from home_companian.domain import Rect, SlotAssignment
from home_companian.modules.treasure_hunt import TreasureHuntModule
from home_companian.treasure_hunt import TreasureHuntStore


FONT = Path("/usr/share/fonts/adobe-source-han-sans/SourceHanSansCN-Regular.otf")
BOXES = [
    [0.05, 0.05, 0.4, 0.25],
    [0.55, 0.05, 0.4, 0.25],
    [0.05, 0.375, 0.4, 0.25],
    [0.55, 0.375, 0.4, 0.25],
    [0.05, 0.7, 0.4, 0.25],
    [0.55, 0.7, 0.4, 0.25],
]


class TreasureHuntTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.library = Path(self.temporary_directory.name)
        self.backgrounds = self.library / "treasure_hunt" / "background"
        self.backgrounds.mkdir(parents=True)
        Image.new("RGBA", (100, 80), (160, 160, 160, 128)).save(
            self.library / "treasure_hunt" / "check_grey.png"
        )
        Image.new("L", (300, 320), 240).save(
            self.backgrounds / "background1.png"
        )
        (self.backgrounds / "background1.yaml").write_text(
            "text_boxes:\n"
            + "".join(f"  - {box}\n" for box in BOXES),
            encoding="utf-8",
        )
        self.settings = SimpleNamespace(library_dir=self.library, font=FONT)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_defaults_to_first_background_and_empty_texts(self) -> None:
        hunt = TreasureHuntStore(self.library).load()

        self.assertEqual(hunt.background.name, "background1.png")
        self.assertEqual(hunt.texts, ("",) * 6)
        self.assertEqual(hunt.completed, (False,) * 6)
        self.assertEqual(hunt.background.boxes[0], tuple(BOXES[0]))

    def test_saves_and_loads_current_hunt(self) -> None:
        texts = [f"clue {index}" for index in range(1, 7)]
        store = TreasureHuntStore(self.library)

        store.save("background1.png", texts, [True, False, False, False, False, False])
        loaded = store.load()

        self.assertEqual(loaded.texts, tuple(texts))
        self.assertEqual(loaded.completed, (True, False, False, False, False, False))
        self.assertIn("background1.png", store.current_path.read_text())

    def test_rejects_layout_without_six_boxes(self) -> None:
        (self.backgrounds / "background1.yaml").write_text(
            "text_boxes:\n  - [0, 0, 1, 1]\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ConfigError, "exactly 6"):
            TreasureHuntStore(self.library).backgrounds()

    def test_module_snapshot_and_render(self) -> None:
        TreasureHuntStore(self.library).save(
            "background1.png",
            ["第一条线索", "Second clue", "", "", "", ""],
            [True, False, False, False, False, False],
        )
        module = TreasureHuntModule()
        snapshot = module.prepare(
            self.settings,
            datetime.now(),
            SlotAssignment(1, "treasure_hunt"),
        )

        self.assertEqual(json.loads(snapshot)["background"], "background1.png")
        self.assertTrue(json.loads(snapshot)["completed"][0])
        rendered = module.render(
            self.settings,
            snapshot,
            Rect(0, 0, 400, 400),
            datetime.now(),
        )

        self.assertEqual((rendered.size, rendered.mode), ((400, 400), "L"))
        self.assertLess(rendered.getextrema()[0], 240)

    def test_rejects_more_than_two_hundred_characters(self) -> None:
        with self.assertRaisesRegex(ValueError, "at most 200"):
            TreasureHuntStore(self.library).save(
                "background1.png",
                ["x" * 201, "", "", "", "", ""],
                [False] * 6,
            )

    def test_english_wrap_keeps_words_and_fits_short_word_on_line(self) -> None:
        draw = ImageDraw.Draw(Image.new("L", (400, 100), 255))
        font = ImageFont.truetype(str(FONT), 28)
        width = round(draw.textlength("LOOK UNDER THE", font=font)) + 1

        lines = TreasureHuntModule._wrap_text(
            draw,
            "LOOK UNDER THE TABLE",
            font,
            width,
        )

        self.assertEqual(lines, ["LOOK UNDER THE", "TABLE"])
        self.assertFalse(TreasureHuntModule._starts_with_short_connector(lines))
        self.assertTrue(
            TreasureHuntModule._starts_with_short_connector(
                ["LOOK UNDER", "THE TABLE"]
            )
        )

    def test_explicit_lines_scale_from_longest_line_without_rewrapping(self) -> None:
        text = "6 RED cars\n10 Trees\nName 5 animals"
        image = Image.new("L", (600, 760), 255)

        with patch.object(ImageDraw.ImageDraw, "multiline_text") as draw_text:
            TreasureHuntModule._draw_text(
                image,
                (600, 760),
                (0, 0),
                tuple(BOXES[0]),
                text,
                FONT,
            )

        self.assertEqual(draw_text.call_args.args[1], text)


if __name__ == "__main__":
    unittest.main()
