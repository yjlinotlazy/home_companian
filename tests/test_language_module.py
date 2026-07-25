import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from home_companian.config import ConfigError
from home_companian.domain import Rect, SlotAssignment
from home_companian.modules.language import (
    SYMBOLS,
    LanguageModule,
    load_english_sentences,
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
