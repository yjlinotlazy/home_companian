import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from home_companian.config import ConfigError
from home_companian.domain import Rect, SlotAssignment
from home_companian.modules.language import (
    SYMBOLS,
    LanguageModule,
    load_chinese_poems,
    load_english_sentences,
    load_fill_word_problems,
)


FONT = Path("/usr/share/fonts/adobe-source-han-sans/SourceHanSansCN-Regular.otf")


class LanguageModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.library = Path(self.temporary_directory.name)
        directory = self.library / "language"
        directory.mkdir()
        (directory / "english_sentences.txt").write_text(
            "The little cat sleeps on the warm chair.\n"
            "A happy dog runs after the red ball.\n",
            encoding="utf-8",
        )
        (directory / "fill_words.txt").write_text(
            "（八）月，（人）们\n"
            "(白)云，(红)花\n"
            "（大）山，（小）鸟，（蓝）天\n",
            encoding="utf-8",
        )
        (directory / "chinese_poems.txt").write_text(
            "床前明月光，疑是地上霜，举头望明月，低头思故乡\n"
            "春眠不觉晓，处处闻啼鸟，夜来风雨声，花落知多少\n",
            encoding="utf-8",
        )
        self.settings = SimpleNamespace(
            library_dir=self.library,
            font=FONT,
            latin_font=FONT,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_loads_simple_unique_sentences(self) -> None:
        sentences = load_english_sentences(self.library)
        self.assertEqual(len(sentences), 2)
        self.assertTrue(sentences[0].endswith("."))

    def test_cipher_replaces_two_or_three_letters_respectively(self) -> None:
        snapshot = json.loads(
            LanguageModule().prepare(
                self.settings,
                datetime.now(),
                SlotAssignment(1, "language", (("type", "cipher"),)),
            )
        )

        self.assertEqual(snapshot["type"], "cipher")
        self.assertIn(len(snapshot["mapping"]), {2, 3})
        self.assertEqual(
            [item["symbol"] for item in snapshot["mapping"]],
            list(SYMBOLS[: len(snapshot["mapping"])]),
        )
        self.assertEqual(
            len({item["letter"] for item in snapshot["mapping"]}),
            len(snapshot["mapping"]),
        )
        for item in snapshot["mapping"]:
            self.assertIn(item["symbol"], snapshot["encoded"])
            self.assertIn(item["letter"], snapshot["sentence"].lower())

    def test_loads_fill_words_with_chinese_and_english_parentheses(self) -> None:
        problems = load_fill_word_problems(self.library)

        self.assertEqual(problems[0].answers, ("八", "人"))
        self.assertEqual(problems[0].prompts, ("__月", "__们"))
        self.assertEqual(problems[1].answers, ("白", "红"))
        self.assertEqual(problems[2].answers, ("大", "小", "蓝"))
        self.assertEqual(
            problems[2].prompts,
            ("__山", "__鸟", "__天"),
        )

    def test_fill_words_shuffles_choices_and_uses_chinese_blanks(self) -> None:
        with (
            patch(
                "home_companian.modules.language.random.choice",
                side_effect=lambda values: values[0],
            ),
            patch(
                "home_companian.modules.language.random.shuffle",
                side_effect=lambda values: values.reverse(),
            ),
        ):
            snapshot = json.loads(
                LanguageModule().prepare(
                    self.settings,
                    datetime.now(),
                    SlotAssignment(
                        1,
                        "language",
                        (("type", "fill_words"),),
                    ),
                )
            )

        self.assertEqual(snapshot["options"], ["人", "八"])
        self.assertEqual(snapshot["prompts"], ["__月", "__们"])
        self.assertEqual(snapshot["answers"], ["八", "人"])

    def test_loads_four_clause_chinese_poems(self) -> None:
        poems = load_chinese_poems(self.library)

        self.assertEqual(
            poems[0],
            ("床前明月光", "疑是地上霜", "举头望明月", "低头思故乡"),
        )

    def test_games_rotates_all_language_game_types(self) -> None:
        module = LanguageModule()
        assignment = SlotAssignment(1, "language", (("type", "games"),))

        snapshots = tuple(
            json.loads(module.prepare(self.settings, datetime.now(), assignment))
            for _ in range(3)
        )

        self.assertEqual(
            {snapshot["type"] for snapshot in snapshots},
            {"cipher", "fill_words", "chinese_poem"},
        )

    def test_avoids_repeating_the_same_sentence(self) -> None:
        module = LanguageModule()
        assignment = SlotAssignment(1, "language", (("type", "cipher"),))
        first = json.loads(module.prepare(self.settings, datetime.now(), assignment))
        second = json.loads(module.prepare(self.settings, datetime.now(), assignment))
        self.assertNotEqual(first["sentence"], second["sentence"])

    def test_rejects_invalid_sentence_file(self) -> None:
        (self.library / "language" / "english_sentences.txt").write_text(
            "Too short 123\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ConfigError, "invalid English sentence"):
            load_english_sentences(self.library)

    @unittest.skipUnless(FONT.exists(), "Source Han Sans font is not installed")
    def test_renders_cipher_for_crowpanel(self) -> None:
        module = LanguageModule()
        snapshot = module.prepare(
            self.settings,
            datetime.now(),
            SlotAssignment(1, "language", (("type", "cipher"),)),
        )

        image = module.render(
            self.settings,
            snapshot,
            Rect(0, 0, 792, 228),
            datetime.now(),
        )

        self.assertEqual((image.size, image.mode), ((792, 228), "1"))
        self.assertEqual(image.getextrema(), (0, 255))

    @unittest.skipUnless(FONT.exists(), "Source Han Sans font is not installed")
    def test_renders_three_fill_words_as_two_rows_for_crowpanel(self) -> None:
        snapshot = json.dumps(
            {
                "type": "fill_words",
                "options": ["蓝", "小", "大"],
                "prompts": ["__山", "__鸟", "__天"],
                "answers": ["大", "小", "蓝"],
            },
            ensure_ascii=False,
        )

        image = LanguageModule().render(
            self.settings,
            snapshot,
            Rect(0, 0, 792, 228),
            datetime.now(),
        )

        self.assertEqual((image.size, image.mode), ((792, 228), "1"))
        self.assertEqual(image.getextrema(), (0, 255))

    @unittest.skipUnless(FONT.exists(), "Source Han Sans font is not installed")
    def test_renders_chinese_poem_as_two_rows_for_crowpanel(self) -> None:
        snapshot = json.dumps(
            {
                "type": "chinese_poem",
                "clauses": [
                    "床前明月光",
                    "疑是地上霜",
                    "举头望明月",
                    "低头思故乡",
                ],
            },
            ensure_ascii=False,
        )

        image = LanguageModule().render(
            self.settings,
            snapshot,
            Rect(0, 0, 792, 228),
            datetime.now(),
        )

        self.assertEqual((image.size, image.mode), ((792, 228), "1"))
        self.assertEqual(image.getextrema(), (0, 255))
