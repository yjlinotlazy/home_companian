from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from home_companian.checklists import ChecklistStore
from home_companian.domain import Rect, SlotAssignment
from home_companian.modules.checklist import ChecklistModule


FONT = "/usr/share/fonts/adobe-source-han-sans/SourceHanSansCN-Regular.otf"


class ChecklistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.library = Path(self.temporary_directory.name)
        (self.library / "checklists.csv").write_text(
            "id,group,text\n1,瓜,EAT\n2,瓜,SHOWER\n3,家,CLEAN UP\n",
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
        settings = SimpleNamespace(library_dir=self.library)
        assignment = SlotAssignment(1, "checklist", (("group", "瓜"),))
        module = ChecklistModule()

        before = module.prepare(settings, datetime(2026, 7, 19), assignment)
        self.store.set_completed(1, True, datetime(2026, 7, 19, 9))
        after = module.prepare(settings, datetime(2026, 7, 19), assignment)

        self.assertNotEqual(before, after)
        self.assertIn('"completed":[]', before)
        self.assertIn('"completed":[1]', after)

    @unittest.skipUnless(Path(FONT).exists(), "Source Han Sans font is not installed")
    def test_module_renders_group_with_checkbox_state(self) -> None:
        self.store.set_completed(1, True, datetime(2026, 7, 19, 9))
        settings = SimpleNamespace(
            library_dir=self.library,
            font=Path(FONT),
            latin_font=Path(FONT),
        )
        module = ChecklistModule()
        assignment = SlotAssignment(1, "checklist", (("group", "瓜"),))

        content_id = module.prepare(settings, datetime(2026, 7, 19), assignment)
        image = module.render(
            settings,
            content_id,
            Rect(0, 0, 390, 270),
            datetime(2026, 7, 19),
        )

        self.assertEqual((image.size, image.mode), ((390, 270), "1"))
        self.assertEqual(image.getextrema(), (0, 255))


if __name__ == "__main__":
    unittest.main()
