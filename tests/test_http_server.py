import unittest

from datetime import time
from pathlib import Path

from home_companian.config import FontChoice
from home_companian.http_server import (
    index_html,
    is_random_preview,
    parse_item_id,
    parse_font_name,
    parse_preview_time,
)


class HttpServerTests(unittest.TestCase):
    def test_parses_preview_time(self) -> None:
        self.assertIsNone(parse_preview_time(""))
        self.assertEqual(parse_preview_time("time=12%3A30"), time(12, 30))
        with self.assertRaises(ValueError):
            parse_preview_time("time=25%3A00")

    def test_index_contains_both_preview_controls(self) -> None:
        selected = Path("/fonts/wenkai.ttf")
        page = index_html(
            (
                FontChoice("霞鹜文楷", selected),
                FontChoice("思源黑体", Path("/fonts/sans.otf")),
            ),
            selected,
            (FontChoice("Caskaydia", Path("/fonts/caskaydia.ttf")),),
            Path("/fonts/caskaydia.ttf"),
        )
        self.assertIn("换一个".encode(), page)
        self.assertIn("定时预览".encode(), page)
        self.assertIn("更改".encode(), page)
        self.assertIn("已设为下次刷新".encode(), page)
        self.assertIn(b'type="time"', page)
        self.assertIn("霞鹜文楷".encode(), page)
        self.assertIn("英文字体".encode(), page)
        self.assertIn(b"Caskaydia", page)
        self.assertNotIn("下次刷新预览".encode(), page)
        self.assertIn(b'id="next-refresh-time"', page)
        self.assertIn(b'<option value="\xe9\x9c\x9e\xe9\xb9\x9c\xe6\x96\x87\xe6\xa5\xb7" selected>', page)

    def test_recognizes_random_preview(self) -> None:
        self.assertTrue(is_random_preview("mode=random"))
        self.assertFalse(is_random_preview(""))

    def test_parses_item_id(self) -> None:
        self.assertIsNone(parse_item_id(""))
        self.assertEqual(parse_item_id("item=3"), 3)
        for query in ("item=0", "item=-1", "item=nope"):
            with self.subTest(query=query), self.assertRaises(ValueError):
                parse_item_id(query)

    def test_parses_font_name(self) -> None:
        self.assertEqual(parse_font_name("name=%E6%96%87%E6%A5%B7"), "文楷")
        self.assertIsNone(parse_font_name(""))


if __name__ == "__main__":
    unittest.main()
