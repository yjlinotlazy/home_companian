from datetime import date, datetime, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from PIL import Image

from home_companian.checklists import ChecklistStore
from home_companian.config import ChecklistGroup, RewardConfig
from home_companian.domain import Rect, SlotAssignment
from home_companian.modules.checklist import ChecklistModule


FONT = "/usr/share/fonts/adobe-source-han-sans/SourceHanSansCN-Regular.otf"


class ChecklistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.library = Path(self.temporary_directory.name)
        (self.library / "checklists.csv").write_text(
            "id,type,text\n"
            "1,personal,EAT\n"
            "2,personal,SHOWER\n"
            "3,family_task,CLEAN UP\n",
            encoding="utf-8",
        )
        self.store = ChecklistStore(self.library)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_completion_is_visible_only_on_its_date_and_history_is_retained(self) -> None:
        self.store.set_completed(1, True, datetime(2026, 7, 19, 9, 30))

        self.assertEqual(self.store.completed_ids(datetime(2026, 7, 19).date()), {1})
        self.assertEqual(self.store.completed_ids(datetime(2026, 7, 20).date()), set())
        self.assertEqual(len(self.store.completions()), 1)

    def test_unchecking_removes_only_todays_completion(self) -> None:
        self.store.set_completed(1, True, datetime(2026, 7, 18, 9))
        self.store.set_completed(1, True, datetime(2026, 7, 19, 9))
        self.store.set_completed(1, False, datetime(2026, 7, 19, 10))

        self.assertEqual(self.store.completed_ids(datetime(2026, 7, 18).date()), {1})
        self.assertEqual(self.store.completed_ids(datetime(2026, 7, 19).date()), set())

    def test_prepared_snapshot_does_not_change_after_store_update(self) -> None:
        settings = SimpleNamespace(
            library_dir=self.library,
            checklist_groups=(ChecklistGroup("person_1", (1, 2)),),
        )
        assignment = SlotAssignment(1, "checklist", (("group", "person_1"),))
        module = ChecklistModule()

        before = module.prepare(settings, datetime(2026, 7, 19), assignment)
        self.store.set_completed(1, True, datetime(2026, 7, 19, 9))
        after = module.prepare(settings, datetime(2026, 7, 19), assignment)

        self.assertNotEqual(before, after)
        self.assertIn('"completed":[]', before)
        self.assertIn('"completed":[1]', after)

    def test_daily_limit_selects_two_stable_items_from_the_whole_group(self) -> None:
        group = ChecklistGroup("family", (1, 2, 3), daily_limit=2)
        settings = SimpleNamespace(
            library_dir=self.library,
            checklist_groups=(group,),
        )
        assignment = SlotAssignment(1, "checklist", (("group", "family"),))
        module = ChecklistModule()
        start = date(2026, 7, 21)

        selections = {
            tuple(
                json.loads(
                    module.prepare(
                        settings,
                        datetime.combine(start + timedelta(days=offset), datetime.min.time()),
                        assignment,
                    )
                )["item_ids"]
            )
            for offset in range(7)
        }

        self.assertTrue(all(len(selection) == 2 for selection in selections))
        self.assertGreater(len(selections), 1)
        self.assertEqual(group.item_ids_for(start), group.item_ids_for(start))

    def test_personal_and_family_tasks_record_one_and_two_points(self) -> None:
        self.store.set_completed(1, True, datetime(2026, 7, 19, 9))
        self.store.set_completed(3, True, datetime(2026, 7, 19, 10))

        self.assertEqual(
            [(row.item_id, row.points) for row in self.store.completions()],
            [(1, 1), (3, 2)],
        )

    def test_reward_caps_at_cost_and_redeeming_resets_without_carry(self) -> None:
        reward = RewardConfig("toy", "玩具", 3)
        self.store.set_completed(1, True, datetime(2026, 7, 19, 9))
        self.store.set_completed(3, True, datetime(2026, 7, 19, 10))
        self.store.set_completed(2, True, datetime(2026, 7, 19, 11))

        self.assertEqual(
            self.store.reward_score(reward, datetime(2026, 7, 19, 12)),
            3,
        )
        self.store.redeem(reward, datetime(2026, 7, 19, 12))
        self.assertEqual(
            self.store.reward_score(reward, datetime(2026, 7, 19, 13)),
            0,
        )

    def test_reward_cannot_be_redeemed_before_full(self) -> None:
        reward = RewardConfig("toy", "玩具", 50)
        self.store.set_completed(1, True, datetime(2026, 7, 19, 9))

        with self.assertRaisesRegex(ValueError, "not enough points"):
            self.store.redeem(reward, datetime(2026, 7, 19, 10))

    def test_initial_points_apply_only_before_first_redemption(self) -> None:
        reward = RewardConfig("toy", "玩具", 3, 2)
        self.store.set_completed(1, True, datetime(2026, 7, 19, 9))

        self.assertEqual(
            self.store.reward_score(reward, datetime(2026, 7, 19, 10)),
            3,
        )
        self.store.redeem(reward, datetime(2026, 7, 19, 10))
        self.assertEqual(
            self.store.reward_score(reward, datetime(2026, 7, 19, 11)),
            0,
        )

    @unittest.skipUnless(Path(FONT).exists(), "Source Han Sans font is not installed")
    def test_module_renders_group_with_checkbox_state(self) -> None:
        self.store.set_completed(1, True, datetime(2026, 7, 19, 9))
        settings = SimpleNamespace(
            library_dir=self.library,
            font=Path(FONT),
            latin_font=Path(FONT),
            checklist_groups=(ChecklistGroup("person_1", (1, 2)),),
        )
        module = ChecklistModule()
        assignment = SlotAssignment(1, "checklist", (("group", "person_1"),))

        content_id = module.prepare(settings, datetime(2026, 7, 19), assignment)
        image = module.render(
            settings,
            content_id,
            Rect(0, 0, 390, 270),
            datetime(2026, 7, 19),
        )

        self.assertEqual((image.size, image.mode), ((390, 270), "1"))
        self.assertEqual(image.getextrema(), (0, 255))

    @unittest.skipUnless(Path(FONT).exists(), "Source Han Sans font is not installed")
    def test_module_uses_heart_images_for_checklist_state(self) -> None:
        decorations = self.library / "decorations"
        decorations.mkdir()
        Image.new("L", (100, 100), 255).save(decorations / "heart.png")
        Image.new("L", (100, 100), 0).save(
            decorations / "heart_completed.png"
        )
        settings = SimpleNamespace(
            library_dir=self.library,
            font=Path(FONT),
            latin_font=Path(FONT),
            checklist_groups=(ChecklistGroup("person_1", (1,)),),
        )
        assignment = SlotAssignment(1, "checklist", (("group", "person_1"),))
        module = ChecklistModule()
        now = datetime(2026, 7, 21, 9)

        before = module.render(
            settings,
            module.prepare(settings, now, assignment),
            Rect(0, 0, 390, 270),
            now,
        )
        self.store.set_completed(1, True, now)
        after = module.render(
            settings,
            module.prepare(settings, now, assignment),
            Rect(0, 0, 390, 270),
            now,
        )

        self.assertEqual(before.crop((22, 71, 51, 100)).getextrema(), (255, 255))
        self.assertEqual(after.crop((22, 71, 51, 100)).getextrema(), (0, 0))
        self.assertEqual(before.getpixel((20, 70)), 255)
        self.assertEqual(after.getpixel((20, 70)), 0)

    @unittest.skipUnless(Path(FONT).exists(), "Source Han Sans font is not installed")
    def test_portrait_replaces_group_title(self) -> None:
        portraits = self.library / "portraits"
        portraits.mkdir()
        portrait = Image.new("L", (120, 100), 255)
        for x in range(20, 100):
            portrait.putpixel((x, 50), 0)
        portrait.save(portraits / "person_1.png")
        settings = SimpleNamespace(
            library_dir=self.library,
            font=Path(FONT),
            latin_font=Path(FONT),
            checklist_groups=(ChecklistGroup("person_1", (1, 2)),),
        )
        assignment = SlotAssignment(
            1,
            "checklist",
            (("group", "person_1"), ("portrait", "portraits/person_1.png")),
        )

        module = ChecklistModule()
        content_id = module.prepare(settings, datetime(2026, 7, 19), assignment)
        image = module.render(
            settings,
            content_id,
            Rect(0, 0, 390, 270),
            datetime(2026, 7, 19),
        )

        self.assertIn('"portrait":"portraits/person_1.png"', content_id)
        self.assertEqual(image.crop((200, 0, 390, 270)).getextrema(), (0, 255))

    @unittest.skipUnless(Path(FONT).exists(), "Source Han Sans font is not installed")
    def test_module_renders_capped_reward_progress(self) -> None:
        self.store.set_completed(1, True, datetime(2026, 7, 19, 9))
        self.store.set_completed(3, True, datetime(2026, 7, 19, 10))
        settings = SimpleNamespace(
            library_dir=self.library,
            font=Path(FONT),
            latin_font=Path(FONT),
            reward=RewardConfig("toy", "玩具", 3),
            checklist_groups=(ChecklistGroup("family", (3,)),),
        )
        module = ChecklistModule()
        assignment = SlotAssignment(
            3,
            "checklist",
            (("group", "family"), ("reward", "toy")),
        )

        content_id = module.prepare(settings, datetime(2026, 7, 19, 12), assignment)
        image = module.render(
            settings,
            content_id,
            Rect(0, 0, 390, 270),
            datetime(2026, 7, 19, 12),
        )

        self.assertIn('"score":3', content_id)
        self.assertEqual(image.crop((0, 210, 390, 270)).getextrema(), (0, 255))


if __name__ == "__main__":
    unittest.main()
