from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

from home_companian.config import ConfigError
from home_companian.domain import Rect, SlotAssignment
from home_companian.modules.health import HealthModule, load_exercises


FONT = Path("/usr/share/fonts/adobe-source-han-sans/SourceHanSansCN-Regular.otf")


class HealthModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.library = Path(self.temporary_directory.name)
        health = self.library / "health"
        health.mkdir()
        (health / "exercises.csv").write_text(
            "id,name,dose,instruction\n"
            "1,深蹲,10次,膝盖朝脚尖方向\n"
            "2,臀桥,10次,缓慢抬起臀部\n",
            encoding="utf-8",
        )
        for exercise_id in (1, 2):
            directory = health / "images" / str(exercise_id)
            directory.mkdir(parents=True)
            Image.new("L", (600, 400), 255).save(directory / "1.png")
            image = Image.new("L", (600, 400), 255)
            image.paste(0, (200, 100, 400, 300))
            image.save(directory / "2.png")
        self.settings = SimpleNamespace(library_dir=self.library, font=FONT)
        self.assignment = SlotAssignment(1, "health")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_loads_exercises(self) -> None:
        exercises = load_exercises(self.library)
        self.assertEqual([exercise.name for exercise in exercises], ["深蹲", "臀桥"])

    def test_random_selection_avoids_immediate_repeat(self) -> None:
        module = HealthModule()
        with patch(
            "home_companian.modules.health.random.choice",
            side_effect=lambda values: values[0],
        ):
            first = module.prepare(self.settings, datetime.now(), self.assignment)
            second = module.prepare(self.settings, datetime.now(), self.assignment)
        self.assertEqual((first, second), (1, 2))

    @unittest.skipUnless(FONT.exists(), "Source Han Sans font is not installed")
    def test_renders_wide_and_compact_slots(self) -> None:
        module = HealthModule()
        wide = module.render(
            self.settings, 1, Rect(0, 0, 792, 228), datetime.now()
        )
        compact = module.render(
            self.settings, 1, Rect(0, 0, 200, 200), datetime.now()
        )
        self.assertEqual((wide.size, wide.mode), ((792, 228), "1"))
        self.assertEqual((compact.size, compact.mode), ((200, 200), "1"))
        self.assertEqual(wide.getextrema(), (0, 255))
        self.assertEqual(compact.getextrema(), (0, 255))

    def test_rejects_invalid_csv_header(self) -> None:
        (self.library / "health" / "exercises.csv").write_text(
            "id,name\n1,深蹲\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(ConfigError, "must use"):
            load_exercises(self.library)


if __name__ == "__main__":
    unittest.main()
