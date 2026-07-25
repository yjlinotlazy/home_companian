import unittest
from unittest.mock import Mock

from datetime import time
from datetime import datetime
from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from home_companian.checklists import ChecklistItem
from home_companian.config import FontChoice, RewardConfig
from home_companian.devices import KINDLE_6_167PPI_LANDSCAPE
from home_companian.forge.engine import Forge
from home_companian.http_server import (
    DISPLAY_BIN_DEVICE_ID,
    DevicePage,
    device_preview_png,
    index_html,
    is_random_preview,
    make_handler,
    parse_item_id,
    parse_checklist_route,
    parse_reward_route,
    request_source_ip,
    parse_device_route,
    parse_font_name,
    parse_preview_id,
    parse_preview_time,
)
from home_companian.service import RewardStatus


class HttpServerTests(unittest.TestCase):
    def test_display_bin_remains_bound_to_wall_panel(self) -> None:
        self.assertEqual(DISPLAY_BIN_DEVICE_ID, "wall_panel")

    def test_request_source_ip_trusts_forwarding_only_from_loopback(self) -> None:
        self.assertEqual(
            request_source_ip("127.0.0.1", "192.0.2.10, 127.0.0.1"),
            "192.0.2.10",
        )
        self.assertEqual(
            request_source_ip("192.0.2.20", "198.51.100.30"),
            "192.0.2.20",
        )
        self.assertEqual(request_source_ip("::1", "bad"), "::1")

    def test_parses_device_routes(self) -> None:
        self.assertEqual(
            parse_device_route("/v1/devices/kindleGen7dk/next", "next"),
            "kindleGen7dk",
        )
        self.assertEqual(parse_device_route("/v1/devices/wall/ack", "ack"), "wall")
        self.assertEqual(
            parse_device_route("/v1/devices/kindleGen7dk/refresh", "refresh"),
            "kindleGen7dk",
        )
        self.assertIsNone(parse_device_route("/display.bin", "next"))

    def test_parses_checklist_route(self) -> None:
        self.assertEqual(parse_checklist_route("/v1/checklists/3"), 3)
        self.assertIsNone(parse_checklist_route("/v1/devices/wall/next"))
        with self.assertRaises(ValueError):
            parse_checklist_route("/v1/checklists/nope")

    def test_parses_reward_redemption_route(self) -> None:
        self.assertEqual(parse_reward_route("/v1/rewards/toy/redeem"), "toy")
        self.assertIsNone(parse_reward_route("/v1/checklists/1"))

    def test_kindle_browser_preview_stays_in_logical_landscape_orientation(self) -> None:
        source = Image.new("RGB", (800, 600), "white")
        frame = Forge().encode(
            source,
            "scene-1",
            KINDLE_6_167PPI_LANDSCAPE,
            datetime(2026, 7, 19),
        )
        rendered = SimpleNamespace(image=source, frame=frame)

        payload = device_preview_png(rendered)

        self.assertEqual(payload[24], 8)  # PNG IHDR bit depth
        self.assertEqual(payload[25], 0)  # PNG IHDR grayscale color type
        with Image.open(BytesIO(payload)) as image:
            self.assertEqual(image.mode, "L")
            self.assertEqual(image.size, (800, 600))
        with Image.open(BytesIO(frame.payload)) as image:
            self.assertEqual(image.size, (600, 800))

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
            (DevicePage("wall_panel", "crowpanel_579", 792, 272, True),),
            (("person_1", ChecklistItem(1, "personal", "EAT"), True),),
            RewardStatus(RewardConfig("toy", "玩具", 50), 50),
        )
        self.assertIn("换一个".encode(), page)
        self.assertIn("定时预览".encode(), page)
        self.assertIn("更改".encode(), page)
        self.assertIn("已设为下次刷新".encode(), page)
        self.assertIn("继续当前".encode(), page)
        self.assertIn("已沿用到下次刷新".encode(), page)
        self.assertIn(b"continue-current", page)
        self.assertIn(b'type="time"', page)
        self.assertIn("霞鹜文楷".encode(), page)
        self.assertIn("英文字体".encode(), page)
        self.assertIn(b"Caskaydia", page)
        self.assertNotIn("下次刷新预览".encode(), page)
        self.assertIn(b"data-next-refresh-time", page)
        self.assertIn(b"/v1/devices/", page)
        self.assertIn(b'<option value="\xe9\x9c\x9e\xe9\xb9\x9c\xe6\x96\x87\xe6\xa5\xb7" selected>', page)
        self.assertIn("今日清单".encode(), page)
        self.assertIn(b'data-checklist-id="1" checked', page)
        self.assertIn(b'data-reward-id="toy"', page)
        self.assertIn(b'data-action="redeem-reward"', page)
        self.assertNotIn(b'data-action="redeem-reward" disabled', page)
        self.assertIn(b"progress.setAttribute('value', String(reward.score))", page)
        self.assertIn(b"progress.setAttribute('value', '0')", page)
        self.assertIn("寻宝游戏".encode(), page)
        self.assertEqual(page.count(b"<textarea data-treasure-text="), 6)
        self.assertIn(b'data-mode-section-title="treasure_hunt"', page)
        self.assertNotIn("显示寻宝游戏".encode(), page)
        self.assertNotIn("返回任务板".encode(), page)
        self.assertEqual(
            page.count(b'<input type="checkbox" data-treasure-completed="'),
            6,
        )
        self.assertIn(b'data-treasure-rendered-preview', page)
        self.assertIn(b'width="300" height="400"', page)
        self.assertIn(b'width:min(300px,100%)', page)
        self.assertIn(b'body { margin:1rem !important; }', page)

    def test_index_stacks_crowpanel_then_kindle(self) -> None:
        page = index_html(
            (),
            Path("/fonts/wenkai.ttf"),
            (),
            Path("/fonts/latin.ttf"),
            devices=(
                DevicePage("wall_panel", "crowpanel_579", 792, 272, True),
                DevicePage(
                    "kindleGen7dk",
                    "kindle_6_167ppi_landscape",
                    800,
                    600,
                    False,
                    False,
                ),
            ),
        ).decode()

        divider = page.index('<hr class="device-divider">')
        self.assertLess(page.index("<h2>CrowPanel"), divider)
        self.assertLess(divider, page.index("<h2>Kindle"))
        self.assertIn('/v1/devices/wall_panel/preview.png', page)
        self.assertIn('/v1/devices/kindleGen7dk/taskboard-preview.png', page)
        self.assertIn("<p data-unconfirmed>设备尚未确认显示画面</p>", page)
        self.assertEqual(
            page.count('<button type="button" data-action="random-preview">'), 1
        )
        self.assertEqual(page.count("<img data-next-preview"), 2)
        self.assertEqual(page.count("data-next-refresh-time"), 2)
        self.assertIn('data-action="refresh-rendered">手动刷新</button>', page)
        self.assertEqual(
            page.count('<button type="button" data-action="continue-current"'),
            1,
        )
        self.assertIn('<select data-display-mode>', page)
        self.assertIn('data-action="apply-display-mode">确定</button>', page)
        self.assertIn('data-mode-section-title="taskboard">任务板</h3>', page)
        self.assertIn("--preview-width:396px", page)
        self.assertIn("--preview-width:400px", page)

    def test_recognizes_random_preview(self) -> None:
        self.assertTrue(is_random_preview("mode=random"))
        self.assertFalse(is_random_preview(""))

    def test_parses_item_id(self) -> None:
        self.assertIsNone(parse_item_id(""))
        self.assertEqual(parse_item_id("item=3"), 3)
        for query in ("item=0", "item=-1", "item=nope"):
            with self.subTest(query=query), self.assertRaises(ValueError):
                parse_item_id(query)

    def test_parses_selected_preview_id(self) -> None:
        preview_id = "a" * 64
        self.assertEqual(parse_preview_id(f"id={preview_id}"), preview_id)
        for query in ("", "id=short", f"id={'A' * 64}"):
            with self.subTest(query=query), self.assertRaises(ValueError):
                parse_preview_id(query)

    def test_rejects_incomplete_json_body(self) -> None:
        handler_type = make_handler(SimpleNamespace(), SimpleNamespace())
        handler = handler_type.__new__(handler_type)
        handler.headers = {"Content-Length": "2"}
        handler.rfile = BytesIO(b"")

        with self.assertRaisesRegex(ValueError, "incomplete JSON body"):
            handler._read_json()

    def test_send_ignores_disconnected_client(self) -> None:
        handler_type = make_handler(SimpleNamespace(), SimpleNamespace())
        handler = handler_type.__new__(handler_type)
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.wfile = SimpleNamespace(write=Mock(side_effect=BrokenPipeError))
        handler.close_connection = False

        handler._send(HTTPStatus.BAD_REQUEST, "text/plain", b"bad request")

        self.assertTrue(handler.close_connection)

    def test_parses_font_name(self) -> None:
        self.assertEqual(parse_font_name("name=%E6%96%87%E6%A5%B7"), "文楷")
        self.assertIsNone(parse_font_name(""))


if __name__ == "__main__":
    unittest.main()
