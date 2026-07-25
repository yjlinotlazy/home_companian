import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from home_companian.config import ConfigError
from home_companian.domain import Rect, SlotAssignment
from home_companian.modules.creative import CreativeModule, load_creative_prompts


FONT = Path("/usr/share/fonts/adobe-source-han-sans/SourceHanSansCN-Regular.otf")


class CreativeModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.library = Path(self.temporary_directory.name)
        directory = self.library / "creative"
        directory.mkdir()
        (directory / "chinese.txt").write_text("天\n地\n山\n水\n风\n雨\n", encoding="utf-8")
        (directory / "english.txt").write_text(
            "cat\ndog\ntree\nmoon\nbook\nrun\n",
            encoding="utf-8",
        )
        self.settings = SimpleNamespace(
            library_dir=self.library,
            font=FONT,
            latin_font=FONT,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_loads_elementary_prompt_files(self) -> None:
        self.assertEqual(
            load_creative_prompts(self.library, "chinese")[:4],
            ("天", "地", "山", "水"),
        )
        self.assertEqual(
            load_creative_prompts(self.library, "english")[:4],
            ("cat", "dog", "tree", "moon"),
        )

    def test_prepares_four_unique_prompts_for_each_language(self) -> None:
        module = CreativeModule()
        for language in ("chinese", "english"):
            snapshot = json.loads(
                module.prepare(
                    self.settings,
                    datetime.now(),
                    SlotAssignment(
                        1,
                        "creative",
                        (("language", language),),
                    ),
                )
            )
            self.assertEqual(snapshot["language"], language)
            self.assertEqual(len(snapshot["items"]), 4)
            self.assertEqual(len(set(snapshot["items"])), 4)

    def test_random_language_selects_one_version(self) -> None:
        snapshot = json.loads(
            CreativeModule().prepare(
                self.settings,
                datetime.now(),
                SlotAssignment(1, "creative", (("language", "random"),)),
            )
        )
        self.assertIn(snapshot["language"], {"chinese", "english"})

    def test_rejects_invalid_prompt_content(self) -> None:
        (self.library / "creative" / "chinese.txt").write_text(
            "天空\n地\n山\n水\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ConfigError, "one Chinese character"):
            load_creative_prompts(self.library, "chinese")

    @unittest.skipUnless(FONT.exists(), "Source Han Sans font is not installed")
    def test_renders_crowpanel_wide_layout(self) -> None:
        module = CreativeModule()
        content_id = module.prepare(
            self.settings,
            datetime.now(),
            SlotAssignment(1, "creative", (("language", "english"),)),
        )

        image = module.render(
            self.settings,
            content_id,
            Rect(0, 0, 792, 228),
            datetime.now(),
        )

        self.assertEqual((image.size, image.mode), ((792, 228), "1"))
        self.assertEqual(image.getextrema(), (0, 255))
