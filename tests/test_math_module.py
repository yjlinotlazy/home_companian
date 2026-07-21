import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from home_companian.config import ConfigError
from home_companian.domain import Rect, SlotAssignment
from home_companian.modules.math import MathModule, load_math_problems, solve_game24


FONT = Path("/usr/share/fonts/adobe-source-han-sans/SourceHanSansCN-Regular.otf")


class MathModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.library = Path(self.temporary_directory.name)
        directory = self.library / "math"
        directory.mkdir()
        (directory / "problems.csv").write_text(
            "id,type,question,answer\n"
            "1,arithmetic,6 × 8 = ?,48\n"
            "2,thinking,找规律：2，4，8，？,16\n"
            "3,arithmetic,7 + 8 = ?,15\n",
            encoding="utf-8",
        )
        self.settings = SimpleNamespace(library_dir=self.library, font=FONT, latin_font=FONT)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_loads_stored_problem_types(self) -> None:
        problems = load_math_problems(self.library)
        self.assertEqual(
            [problem.type for problem in problems],
            ["arithmetic", "thinking", "arithmetic"],
        )
        self.assertEqual(problems[1].answer, "16")

    def test_filters_problem_type(self) -> None:
        module = MathModule()
        selected = module.prepare(
            self.settings,
            datetime.now(),
            SlotAssignment(1, "math", (("type", "thinking"),)),
        )
        self.assertEqual(selected, 2)

    def test_random_selection_avoids_immediate_repeat(self) -> None:
        module = MathModule()
        assignment = SlotAssignment(1, "math", (("type", "arithmetic"),))
        with patch(
            "home_companian.modules.math.random.choice",
            side_effect=lambda values: values[0],
        ):
            first = module.prepare(self.settings, datetime.now(), assignment)
            second = module.prepare(self.settings, datetime.now(), assignment)
        self.assertEqual((first, second), (1, 3))

    def test_generates_solvable_game24_without_division(self) -> None:
        module = MathModule()
        snapshot = json.loads(
            module.prepare(
                self.settings,
                datetime.now(),
                SlotAssignment(1, "math", (("type", "game24"),)),
            )
        )

        self.assertEqual(snapshot["type"], "game24")
        self.assertEqual(len(snapshot["numbers"]), 4)
        self.assertTrue(all(1 <= number <= 9 for number in snapshot["numbers"]))
        self.assertNotIn("/", snapshot["answer"])
        self.assertNotIn("÷", snapshot["answer"])
        self.assertEqual(solve_game24(tuple(sorted(snapshot["numbers"]))), snapshot["answer"])

    def test_game24_avoids_immediate_repeat(self) -> None:
        module = MathModule()
        assignment = SlotAssignment(1, "math", (("type", "game24"),))
        first = json.loads(module.prepare(self.settings, datetime.now(), assignment))
        second = json.loads(module.prepare(self.settings, datetime.now(), assignment))
        self.assertNotEqual(sorted(first["numbers"]), sorted(second["numbers"]))

    @unittest.skipUnless(FONT.exists(), "Source Han Sans font is not installed")
    def test_renders_game24_as_numbers_only(self) -> None:
        content_id = MathModule().prepare(
            self.settings,
            datetime.now(),
            SlotAssignment(1, "math", (("type", "game24"),)),
        )
        rendered = MathModule().render(
            self.settings, content_id, Rect(0, 0, 792, 228), datetime.now()
        )
        self.assertEqual((rendered.size, rendered.mode), ((792, 228), "1"))
        self.assertEqual(rendered.getextrema(), (0, 255))

    @unittest.skipUnless(FONT.exists(), "Source Han Sans font is not installed")
    def test_renders_question_without_answer(self) -> None:
        rendered = MathModule().render(
            self.settings, 2, Rect(0, 0, 792, 228), datetime.now()
        )
        self.assertEqual((rendered.size, rendered.mode), ((792, 228), "1"))
        self.assertEqual(rendered.getextrema(), (0, 255))

    def test_rejects_unknown_problem_type(self) -> None:
        with self.assertRaisesRegex(ConfigError, "type must be"):
            MathModule().prepare(
                self.settings,
                datetime.now(),
                SlotAssignment(1, "math", (("type", "geometry"),)),
            )


if __name__ == "__main__":
    unittest.main()
