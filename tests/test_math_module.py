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
from home_companian.modules.math_games import PatternGame


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

    def test_generates_five_item_pattern_with_hidden_sixth_answer(self) -> None:
        snapshot = json.loads(
            MathModule().prepare(
                self.settings,
                datetime.now(),
                SlotAssignment(1, "math", (("type", "pattern"),)),
            )
        )

        self.assertEqual(snapshot["type"], "pattern")
        self.assertEqual(len(snapshot["items"]), 5)
        self.assertTrue(all(isinstance(item, str) and item for item in snapshot["items"]))
        self.assertIsInstance(snapshot["answer"], str)
        self.assertTrue(snapshot["answer"])

    def test_pattern_families_have_unambiguous_sixth_item(self) -> None:
        generators = (
            PatternGame._count_up,
            PatternGame._count_down,
            PatternGame._alternating,
            PatternGame._repeat_symbols,
            PatternGame._repeat_symbol_triple,
            PatternGame._repeat_symbol_pair,
            PatternGame._rotate_directions,
            PatternGame._repeat_words,
            PatternGame._alternating_steps,
            PatternGame._growing_steps,
        )
        for generator in generators:
            family, values = generator()
            self.assertEqual(len(values), 6, family)
            if family in {"alternating", "symbols"}:
                self.assertEqual(values[5], values[1])
            elif family in {"words", "symbol_triple", "symbol_pair"}:
                self.assertEqual(values[5], values[2])
            elif family == "directions":
                self.assertEqual(values[5], values[1])
            elif family == "count_up":
                numbers = tuple(map(int, values))
                self.assertEqual(len(set(b - a for a, b in zip(numbers, numbers[1:]))), 1)
                self.assertGreater(numbers[1], numbers[0])
            elif family == "count_down":
                numbers = tuple(map(int, values))
                self.assertEqual(len(set(a - b for a, b in zip(numbers, numbers[1:]))), 1)
                self.assertGreater(numbers[0], numbers[1])
            elif family == "alternating_steps":
                numbers = tuple(map(int, values))
                steps = tuple(b - a for a, b in zip(numbers, numbers[1:]))
                self.assertEqual((steps[0], steps[1], steps[0], steps[1], steps[0]), steps)
            elif family == "growing_steps":
                numbers = tuple(map(int, values))
                self.assertEqual(
                    tuple(b - a for a, b in zip(numbers, numbers[1:])),
                    (1, 2, 3, 4, 5),
                )

    def test_games_group_rotates_generated_game_types(self) -> None:
        module = MathModule()
        assignment = SlotAssignment(1, "math", (("type", "games"),))
        first = json.loads(module.prepare(self.settings, datetime.now(), assignment))
        second = json.loads(module.prepare(self.settings, datetime.now(), assignment))
        self.assertEqual({first["type"], second["type"]}, {"game24", "pattern"})

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
    def test_renders_pattern_as_five_items_and_question_mark(self) -> None:
        content_id = json.dumps(
            {
                "type": "pattern",
                "family": "words",
                "items": ["猫", "狗", "兔", "猫", "狗"],
                "answer": "兔",
            },
            ensure_ascii=False,
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
