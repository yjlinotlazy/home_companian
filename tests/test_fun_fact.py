import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from PIL import Image

from home_companian.domain import Rect, SlotAssignment
from home_companian.fun_fact_selection import FunFactSelectionStore
from home_companian.modules.fun_fact import FunFactModule, load_fun_facts


FONT = Path("/usr/share/fonts/adobe-source-han-sans/SourceHanSansCN-Regular.otf")


class FunFactModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.library = Path(self.temporary_directory.name)
        directory = self.library / "fun_fact"
        directory.mkdir()
        (directory / "police_station.md").write_text(
            "# Police Station Fun Fact\n\n"
            "- Someone is on duty even at night\n"
            "- Police officers write a lot there\n",
            encoding="utf-8",
        )
        Image.new("RGBA", (300, 200), "white").save(
            directory / "police_station.png"
        )
        self.settings = SimpleNamespace(
            library_dir=self.library,
            font=FONT,
            latin_font=FONT,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_loads_markdown_and_same_stem_image(self) -> None:
        fact = load_fun_facts(self.library)[0]

        self.assertEqual(fact.title, "Police Station Fun Fact")
        self.assertEqual(fact.image, "police_station.png")
        self.assertTrue(fact.lines[0].startswith("• "))

    def test_persists_selected_fun_fact(self) -> None:
        store = FunFactSelectionStore(self.library / "selection.yaml")

        self.assertIsNone(store.selected())
        store.select("police_station")

        self.assertEqual(store.selected(), "police_station")

    def test_bullet_does_not_make_english_text_cjk(self) -> None:
        self.assertFalse(FunFactModule._contains_cjk("• English fact"))
        self.assertTrue(FunFactModule._contains_cjk("• 中文知识"))

    @unittest.skipUnless(FONT.exists(), "Source Han Sans font is not installed")
    def test_renders_image_in_landscape_fun_fact(self) -> None:
        module = FunFactModule()
        snapshot = module.prepare(
            self.settings,
            datetime.now(),
            SlotAssignment(1, "fun_fact"),
        )
        parsed = json.loads(snapshot)

        image = module.render(
            self.settings,
            snapshot,
            Rect(0, 0, 800, 560),
            datetime.now(),
        )

        self.assertEqual(parsed["image"], "police_station.png")
        self.assertEqual((image.size, image.mode), ((800, 560), "L"))
        self.assertEqual(image.getextrema(), (0, 255))

    def test_prepares_requested_fun_fact(self) -> None:
        module = FunFactModule()

        snapshot = module.prepare(
            self.settings,
            datetime.now(),
            SlotAssignment(1, "fun_fact", (("name", "police_station"),)),
        )

        self.assertEqual(json.loads(snapshot)["name"], "police_station")


if __name__ == "__main__":
    unittest.main()
