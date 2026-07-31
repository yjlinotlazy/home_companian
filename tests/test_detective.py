import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from PIL import Image, ImageDraw

from home_companian.detective import DEFAULT_HINT_COUNT, DetectiveStore
from home_companian.domain import Rect, SlotAssignment
from home_companian.http_server import index_html
from home_companian.modules.detective import DetectiveModule


FONT = Path("/usr/share/fonts/TTF/LXGWWenKai-Medium.ttf")


class DetectiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.library = Path(self.temporary.name)
        self.bulbs = tuple(self.library / f"bulbs_{index}.png" for index in range(1, 4))
        for index, path in enumerate(self.bulbs):
            image = Image.new("RGBA", (50, 50), (255, 255, 255, 0))
            ImageDraw.Draw(image).ellipse((8, 5, 42, 39), outline="black", width=index + 1)
            image.save(path)
        self.settings = SimpleNamespace(
            library_dir=self.library,
            font=FONT,
            detective_bulbs=self.bulbs,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_defaults_to_six_hints_and_persists_edits(self) -> None:
        store = DetectiveStore(self.library)
        self.assertEqual(len(store.load().hints), DEFAULT_HINT_COUNT)
        self.assertEqual(store.load().title, "")

        saved = store.save(
            "失踪的钥匙",
            "门锁着。",
            "钥匙在花盆里。",
            ["泥土是新的", "窗户未开"],
            [True, False],
        )

        self.assertEqual(store.load(), saved)
        self.assertEqual(saved.visible, (True, False))

        untitled = store.save("", "门锁着。", "钥匙在花盆里。", ["泥土是新的"])
        self.assertEqual(untitled.title, "")

    def test_snapshot_cycles_through_configured_bulbs(self) -> None:
        DetectiveStore(self.library).save(
            "谜案",
            "案情",
            "谜底",
            ["一", "二", "三", "四", "五", "六"],
        )
        module = DetectiveModule()

        snapshot = json.loads(
            module.prepare(
                self.settings,
                datetime(2026, 7, 31),
                SlotAssignment(1, "detective"),
            )
        )

        self.assertEqual(
            snapshot["bulbs"],
            [str(path) for path in self.bulbs] * 2,
        )
        self.assertEqual(snapshot["visible"], [False] * 6)
        self.assertFalse(snapshot["preview"])

        preview = json.loads(
            module.prepare(
                self.settings,
                datetime(2026, 7, 31),
                SlotAssignment(1, "detective", (("preview", "true"),)),
            )
        )
        self.assertTrue(preview["preview"])

    def test_renders_landscape_detective_panel(self) -> None:
        DetectiveStore(self.library).save(
            "失踪的钥匙",
            "书房的门从里面锁住了。",
            "钥匙藏在花盆下面。",
            [f"第 {index} 条线索" for index in range(1, 7)],
        )
        module = DetectiveModule()
        snapshot = module.prepare(
            self.settings,
            datetime(2026, 7, 31),
            SlotAssignment(1, "detective"),
        )

        image = module.render(
            self.settings,
            snapshot,
            Rect(0, 0, 800, 560),
            datetime(2026, 7, 31),
        )

        self.assertEqual(image.size, (800, 560))
        self.assertLess(image.getextrema()[0], 255)

    def test_web_page_has_dynamic_hint_controls(self) -> None:
        page = index_html((), FONT, (), FONT, ()).decode("utf-8")

        self.assertIn('data-mode-section-title="detective"', page)
        self.assertIn("data-detective-add", page)
        self.assertIn("data-detective-save", page)
        self.assertIn("remove.textContent = '−'", page)
        self.assertIn("data-detective-visibility", page)
        self.assertIn("visible ? '隐藏' : '显示'", page)


if __name__ == "__main__":
    unittest.main()
