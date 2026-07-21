from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image
import yaml

from home_companian.checklists import ChecklistStore
from home_companian.service import DisplayService


FONT = "/usr/share/fonts/adobe-source-han-sans/SourceHanSansCN-Regular.otf"


class DisplayServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        (root / "items.csv").write_text(
            "id,type,text\n"
            "1,personal,Walk\n"
            "2,personal,Read\n"
            "3,family_task,Clean\n",
            encoding="utf-8",
        )
        self.config_path = root / "config.yaml"
        self.config_path.write_text(
            f"font: {FONT}\n"
            "library_dir: .\n"
            "default_device: wall\n"
            "channels:\n"
            "  home:\n"
            "    mode: scheduled\n"
            "    schedule:\n"
            "      - {time: '12:00', item: 1}\n"
            "      - {time: '13:00', item: 2}\n"
            "    random_items: [1, 2, 3]\n"
            "devices:\n"
            "  wall:\n"
            "    profile: crowpanel_579\n"
            "    channel: home\n"
            "    refresh:\n"
            "      minutes: 60\n"
            "      active_start: '07:00'\n"
            "      active_end: '22:00'\n"
            "    presentation:\n"
            "      panel:\n"
            "        template: landscape_1\n"
            "        slots:\n"
            "          1: {module: items}\n",
            encoding="utf-8",
        )
        self.current_display_path = root / "current.png"
        self.service = DisplayService(self.config_path, self.current_display_path)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @unittest.skipUnless(Path(FONT).exists(), "Source Han Sans font is not installed")
    def test_change_replaces_next_panel_until_device_consumes_it(self) -> None:
        changed_at = datetime(2026, 7, 15, 12, 30)
        next_at = self.service.change(3, now=changed_at)

        self.assertEqual(next_at, datetime(2026, 7, 15, 13, 0))
        self.assertEqual(
            self.service.render_next(now=datetime(2026, 7, 15, 12, 45)).item_id,
            3,
        )
        self.assertEqual(
            self.service.render(now=datetime(2026, 7, 15, 13, 0)).item_id,
            2,
        )
        self.assertEqual(
            self.service.render(device=True, now=datetime(2026, 7, 15, 13, 0)).item_id,
            3,
        )
        self.assertEqual(
            self.service.render_next(now=datetime(2026, 7, 15, 13, 1)).item_id,
            2,
        )

    def test_change_targets_next_refresh_interval(self) -> None:
        next_at = self.service.change(3, now=datetime(2026, 7, 15, 14, 0))
        self.assertEqual(next_at, datetime(2026, 7, 15, 15, 0))

    @unittest.skipUnless(Path(FONT).exists(), "Source Han Sans font is not installed")
    def test_delivery_repeats_frame_until_display_ack(self) -> None:
        first = self.service.deliver(now=datetime(2026, 7, 15, 12, 30))
        repeated = self.service.deliver(now=datetime(2026, 7, 15, 12, 31))

        self.assertEqual(first.frame.id, repeated.frame.id)
        self.assertIsNone(self.service.render_current())
        self.service.acknowledge(first.frame.id, "displayed")
        current = self.service.render_current()
        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual(current.frame.id, first.frame.id)

    @unittest.skipUnless(Path(FONT).exists(), "Source Han Sans font is not installed")
    def test_manual_refresh_replaces_pending_delivery_with_checklist_state(self) -> None:
        root = self.config_path.parent
        (root / "checklists.csv").write_text(
            "id,type,text\n1,personal,EAT\n",
            encoding="utf-8",
        )
        raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        raw["checklists"] = {"daily": [1]}
        raw["channels"]["home"]["mode"] = "random"
        raw["devices"]["wall"]["presentation"]["panel"]["slots"] = {
            1: {"module": "checklist", "group": "daily"}
        }
        self.config_path.write_text(
            yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        now = datetime(2026, 7, 21, 10, 0)
        before = self.service.deliver(now)

        self.service.set_checklist_completed(1, True, now)
        refreshed = self.service.refresh_delivery(now)
        delivered = self.service.deliver(now)

        self.assertNotEqual(before.frame.id, refreshed.frame.id)
        self.assertNotEqual(before.image.tobytes(), refreshed.image.tobytes())
        self.assertEqual(delivered.frame.id, refreshed.frame.id)

    @unittest.skipUnless(Path(FONT).exists(), "Source Han Sans font is not installed")
    def test_next_preview_uses_pending_delivery(self) -> None:
        pending = self.service.deliver(now=datetime(2026, 7, 15, 12, 30))

        preview = self.service.preview_next_delivery(
            now=datetime(2026, 7, 15, 12, 45)
        )

        self.assertEqual(preview.frame.id, pending.frame.id)

    @unittest.skipUnless(Path(FONT).exists(), "Source Han Sans font is not installed")
    def test_random_change_is_consumed_once_then_prepares_following_panel(self) -> None:
        self.config_path.write_text(
            self.config_path.read_text(encoding="utf-8").replace(
                "mode: scheduled", "mode: random"
            ),
            encoding="utf-8",
        )
        now = datetime(2026, 7, 15, 12, 30)
        self.service.change(3, now=now)
        with patch("home_companian.selection.random.choice", side_effect=lambda values: values[0]):
            self.assertEqual(self.service.render_next(now=now).item_id, 3)
            self.assertEqual(self.service.render(device=True, now=now).item_id, 3)
            self.assertNotEqual(self.service.render_next(now=now).item_id, 3)

    def test_select_font_persists_selected_candidate(self) -> None:
        other_font = self.config_path.parent / "other.ttf"
        other_font.touch()
        content = self.config_path.read_text(encoding="utf-8")
        self.config_path.write_text(
            content.replace(
                f"font: {FONT}\n",
                f"font: {FONT}\nfonts:\n  默认: {FONT}\n  测试: {other_font}\n",
            ),
            encoding="utf-8",
        )

        selected = self.service.select_font("chinese", "测试")
        saved = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))

        self.assertEqual(selected, other_font)
        self.assertEqual(saved["font"], str(other_font))

    def test_next_check_aligns_to_half_hour_during_day(self) -> None:
        self.config_path.write_text(
            self.config_path.read_text(encoding="utf-8").replace(
                "      minutes: 60\n",
                "      minutes: 30\n",
            ),
            encoding="utf-8",
        )
        self.assertEqual(
            self.service.next_check_seconds(datetime(2026, 7, 15, 9, 12)),
            18 * 60,
        )

    def test_next_check_sleeps_through_night(self) -> None:
        self.assertEqual(
            self.service.next_check_seconds(datetime(2026, 7, 15, 22, 0)),
            9 * 60 * 60,
        )

    def test_variable_daily_refresh_schedule_includes_final_boundary(self) -> None:
        raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        raw["devices"]["wall"]["refresh"] = {
            "schedule": [
                {"start": "08:00", "end": "12:00", "minutes": 30},
                {"start": "12:00", "end": "18:00", "minutes": 90},
                {"start": "18:00", "end": "20:00", "minutes": 30},
            ]
        }
        self.config_path.write_text(
            yaml.safe_dump(raw, sort_keys=False),
            encoding="utf-8",
        )

        cases = (
            (datetime(2026, 7, 21, 7, 30), datetime(2026, 7, 21, 8, 0)),
            (datetime(2026, 7, 21, 8, 0), datetime(2026, 7, 21, 8, 30)),
            (datetime(2026, 7, 21, 11, 30), datetime(2026, 7, 21, 12, 0)),
            (datetime(2026, 7, 21, 12, 0), datetime(2026, 7, 21, 13, 30)),
            (datetime(2026, 7, 21, 15, 0), datetime(2026, 7, 21, 16, 30)),
            (datetime(2026, 7, 21, 19, 30), datetime(2026, 7, 21, 20, 0)),
            (datetime(2026, 7, 21, 20, 0), datetime(2026, 7, 22, 8, 0)),
        )
        for now, expected in cases:
            with self.subTest(now=now):
                self.assertEqual(self.service.next_check_at(now), expected)

    @unittest.skipUnless(Path(FONT).exists(), "Source Han Sans font is not installed")
    def test_preview_random_does_not_advance_device_random_state(self) -> None:
        self.config_path.write_text(
            self.config_path.read_text(encoding="utf-8").replace(
                "mode: scheduled", "mode: random"
            ),
            encoding="utf-8",
        )
        with patch("home_companian.selection.random.choice", side_effect=lambda values: values[0]):
            preview = self.service.render(preview_random=True)
            device = self.service.render(device=True)

        self.assertEqual(preview.item_id, 1)
        self.assertEqual(device.item_id, 1)

    @unittest.skipUnless(Path(FONT).exists(), "Source Han Sans font is not installed")
    def test_next_random_preview_is_stable_until_device_consumes_it(self) -> None:
        self.config_path.write_text(
            self.config_path.read_text(encoding="utf-8").replace(
                "mode: scheduled", "mode: random"
            ),
            encoding="utf-8",
        )
        with patch("home_companian.selection.random.choice", side_effect=lambda values: values[0]):
            first_preview = self.service.render_next()
            repeated_preview = self.service.render_next()
            device = self.service.render(device=True)
            following_preview = self.service.render_next()

        self.assertEqual(first_preview.item_id, repeated_preview.item_id)
        self.assertEqual(device.item_id, first_preview.item_id)
        self.assertNotEqual(following_preview.item_id, first_preview.item_id)

    def test_first_random_scene_of_new_day_discards_yesterdays_checklist(self) -> None:
        root = self.config_path.parent
        (root / "checklists.csv").write_text(
            "id,type,text\n1,personal,EAT\n",
            encoding="utf-8",
        )
        raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        raw["checklists"] = {"daily": [1]}
        raw["channels"]["home"]["mode"] = "random"
        raw["devices"]["wall"]["presentation"]["panel"]["slots"] = {
            1: {"module": "checklist", "group": "daily"}
        }
        self.config_path.write_text(
            yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        ChecklistStore(root).set_completed(
            1,
            True,
            datetime(2026, 7, 20, 20, 0),
        )

        yesterday = self.service._peek_next_scene(
            self.service.settings(),
            datetime(2026, 7, 20, 20, 30),
        )
        today = self.service._consume_next_scene(
            self.service.settings(),
            datetime(2026, 7, 21, 7, 0),
        )

        self.assertIn('"completed":[1]', yesterday.scene.fragments[0].content_id)
        self.assertIn('"date":"2026-07-21"', today.scene.fragments[0].content_id)
        self.assertIn('"completed":[]', today.scene.fragments[0].content_id)

    @unittest.skipUnless(Path(FONT).exists(), "Source Han Sans font is not installed")
    def test_random_scene_selects_panel_and_modules_together(self) -> None:
        raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        raw["channels"]["home"]["mode"] = "random"
        presentation = raw["devices"]["wall"]["presentation"]
        dashboard = presentation.pop("panel")
        presentation["panels"] = [
            dashboard,
            {
                "template": "landscape_1",
                "slots": {1: {"module": "math", "type": "game24"}},
            },
        ]
        self.config_path.write_text(
            yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        with patch(
            "home_companian.service.random.choice",
            side_effect=lambda values: values[-1],
        ):
            prepared = self.service._peek_next_scene(
                self.service.settings(), datetime(2026, 7, 15, 12, 30)
            )
            rendered = self.service.render_next(datetime(2026, 7, 15, 12, 30))

        self.assertEqual(prepared.panel.template, "landscape_1")
        self.assertEqual(prepared.scene.fragments[0].module, "math")
        self.assertIn('"type":"game24"', prepared.scene.fragments[0].content_id)
        self.assertEqual(rendered.image.size, (792, 272))

    @unittest.skipUnless(Path(FONT).exists(), "Source Han Sans font is not installed")
    def test_current_display_is_exact_last_device_render(self) -> None:
        self.assertIsNone(self.service.render_current())

        device = self.service.render(
            device=True,
            now=datetime(2026, 7, 15, 12, 30),
        )
        self.service.render_next(now=datetime(2026, 7, 15, 12, 45))
        self.service.render(
            preview_item_id=2,
            preview_time=datetime(2026, 7, 15, 18, 0).time(),
            now=datetime(2026, 7, 15, 18, 0),
        )
        current = self.service.render_current()

        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual(current.item_id, device.item_id)
        self.assertEqual(current.frame.payload, device.frame.payload)
        self.assertEqual(current.image.tobytes(), device.image.tobytes())

    @unittest.skipUnless(Path(FONT).exists(), "Source Han Sans font is not installed")
    def test_restart_keeps_exact_current_display(self) -> None:
        device = self.service.render(device=True, now=datetime(2026, 7, 15, 12, 30))

        restarted = DisplayService(self.config_path, self.current_display_path)
        current = restarted.render_current()

        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual(current.frame.payload, device.frame.payload)
        self.assertEqual(current.image.tobytes(), device.image.tobytes())

    @unittest.skipUnless(Path(FONT).exists(), "Source Han Sans font is not installed")
    def test_panel_assignment_change_invalidates_prepared_panel(self) -> None:
        content = self.config_path.read_text(encoding="utf-8").replace(
            "mode: scheduled", "mode: random"
        )
        self.config_path.write_text(content, encoding="utf-8")
        with patch("home_companian.selection.random.choice", side_effect=lambda values: values[0]):
            prepared = self.service.render_next()
            self.config_path.write_text(
                content.replace(
                    "        slots:\n          1: {module: items}\n",
                    "        slots: {}\n",
                ),
                encoding="utf-8",
            )
            after_change = self.service.render_next()

        self.assertNotEqual(prepared.item_id, 0)
        self.assertEqual(after_change.item_id, 0)

    @unittest.skipUnless(Path(FONT).exists(), "Source Han Sans font is not installed")
    def test_renders_items_and_chinese_in_two_slot_template(self) -> None:
        chinese = self.config_path.parent / "chinese"
        chinese.mkdir()
        (chinese / "full.md").write_text(
            "# 一年级\n天\n# 二年级\n地\n# 三年级\n人\n"
            "# 四年级\n山\n# 五年级\n水\n# 六年级\n月\n",
            encoding="utf-8",
        )
        (chinese / "select.md").write_text("天", encoding="utf-8")
        content = self.config_path.read_text(encoding="utf-8")
        self.config_path.write_text(
            content.replace("template: landscape_1", "template: landscape_2").replace(
                "          1: {module: items}\n",
                "          1: {module: items}\n"
                "          2: {module: chinese, source: select}\n",
            ),
            encoding="utf-8",
        )

        rendered = self.service.render_next(now=datetime(2026, 7, 15, 12, 30))

        self.assertEqual(rendered.image.size, (792, 272))
        self.assertEqual(rendered.image.crop((0, 0, 300, 44)).getextrema(), (255, 255))
        self.assertEqual(rendered.image.crop((300, 0, 492, 44)).getextrema(), (0, 255))
        self.assertEqual(rendered.image.crop((650, 0, 792, 44)).getextrema(), (0, 255))
        self.assertEqual(rendered.image.crop((528, 0, 792, 272)).getextrema(), (0, 255))

    @unittest.skipUnless(Path(FONT).exists(), "Source Han Sans font is not installed")
    def test_restart_clears_change(self) -> None:
        self.service.change(3, now=datetime(2026, 7, 15, 12, 30))
        restarted = DisplayService(self.config_path, self.current_display_path)
        self.assertEqual(
            restarted.render_next(now=datetime(2026, 7, 15, 12, 45)).item_id,
            2,
        )

    @unittest.skipUnless(Path(FONT).exists(), "Source Han Sans font is not installed")
    def test_checklist_change_updates_prepared_frame_without_changing_other_content(self) -> None:
        root = self.config_path.parent
        (root / "checklists.csv").write_text(
            "id,type,text\n"
            "1,personal,EAT\n"
            "2,family_task,READ\n"
            "3,personal,SHOWER\n",
            encoding="utf-8",
        )
        collection = root / "images" / "etc"
        collection.mkdir(parents=True)
        Image.new("1", (100, 100), 255).save(collection / "only.png")
        content = self.config_path.read_text(encoding="utf-8")
        content = content.replace("mode: scheduled", "mode: random")
        content = content.replace(
            "default_device: wall\n",
            "checklists:\n"
            "  person_1: [1]\n"
            "  family: [2]\n"
            "  person_2: [3]\n"
            "default_device: wall\n",
        )
        content = content.replace("profile: crowpanel_579", "profile: kindle_6_167ppi_landscape")
        content = content.replace(
            "        template: landscape_1\n"
            "        slots:\n"
            "          1: {module: items}\n",
            "        template: landscape_5\n"
            "        slots:\n"
            "          1: {module: checklist, group: person_1}\n"
            "          2: {module: checklist, group: family}\n"
            "          3: {module: checklist, group: person_2}\n"
            "          4: {module: images, collection: etc}\n",
        )
        self.config_path.write_text(content, encoding="utf-8")
        now = datetime(2026, 7, 19, 12, 30)

        before = self.service.render_next(now)
        self.service.set_checklist_completed(1, True, now)
        self.service.refresh_prepared_checklists()
        after = self.service.render_next(now)

        self.assertEqual(before.image.mode, "L")
        self.assertNotEqual(before.frame.id, after.frame.id)
        self.assertNotEqual(before.image.tobytes(), after.image.tobytes())


if __name__ == "__main__":
    unittest.main()
