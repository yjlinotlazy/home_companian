from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from home_companian.config import ConfigError
from home_companian.modules.chinese import load_chinese_characters


FULL = """# 一年级
天地人
# 二年级
春风
# 三年级
山川
# 四年级
日月
# 五年级
江河
# 六年级
湖海
"""


class ChineseModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.library = Path(self.temporary_directory.name)
        (self.library / "chinese").mkdir()
        (self.library / "chinese" / "full.md").write_text(FULL, encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_loads_selected_characters_and_deduplicates(self) -> None:
        (self.library / "chinese" / "select.md").write_text(
            "天 地天\n春", encoding="utf-8"
        )
        self.assertEqual(load_chinese_characters(self.library), ("天", "地", "春"))

    def test_rejects_character_outside_full_catalog(self) -> None:
        (self.library / "chinese" / "select.md").write_text("天云", encoding="utf-8")
        with self.assertRaisesRegex(ConfigError, "not in full.md: 云"):
            load_chinese_characters(self.library)

    def test_rejects_non_chinese_content(self) -> None:
        (self.library / "chinese" / "select.md").write_text("天,地", encoding="utf-8")
        with self.assertRaisesRegex(ConfigError, "non-Chinese character"):
            load_chinese_characters(self.library)


if __name__ == "__main__":
    unittest.main()
