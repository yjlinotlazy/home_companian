from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import random
import re
from threading import Lock

from PIL import Image, ImageDraw, ImageFont

from ..config import ConfigError, Settings
from ..domain import Rect, SlotAssignment


SENTENCE = re.compile(r"^[A-Za-z][A-Za-z ,.?!']+$")
SYMBOLS = ("△", "○", "□")


def load_english_sentences(library_dir: Path) -> tuple[str, ...]:
    path = library_dir / "language" / "english_sentences.txt"
    try:
        sentences = tuple(
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    except OSError as exc:
        raise ConfigError(f"language sentence file cannot be opened: {path}") from exc
    if not sentences or len(set(sentences)) != len(sentences):
        raise ConfigError(f"{path} must contain unique sentences")
    for sentence in sentences:
        letters = {character.lower() for character in sentence if character.isalpha()}
        if SENTENCE.fullmatch(sentence) is None or len(letters) < 3:
            raise ConfigError(f"{path} contains an invalid English sentence")
    return sentences


class LanguageModule:
    name = "language"

    def __init__(self) -> None:
        self._last_sentence: str | None = None
        self._lock = Lock()

    def prepare(
        self,
        settings: Settings,
        at: datetime,
        assignment: SlotAssignment,
    ) -> str:
        del at
        if assignment.option("type", "cipher") != "cipher":
            raise ConfigError("language module type must be cipher")
        sentences = load_english_sentences(settings.library_dir)
        with self._lock:
            candidates = tuple(
                sentence
                for sentence in sentences
                if len(sentences) == 1 or sentence != self._last_sentence
            )
            sentence = random.choice(candidates)
            self._last_sentence = sentence

        counts = Counter(character.lower() for character in sentence if character.isalpha())
        repeated = tuple(letter for letter, count in counts.items() if count >= 2)
        candidates_letters = repeated if len(repeated) >= 3 else tuple(counts)
        hidden_count = random.choice((2, 3))
        letters = random.sample(candidates_letters, hidden_count)
        mapping = dict(zip(letters, SYMBOLS[:hidden_count], strict=True))
        encoded = "".join(mapping.get(character.lower(), character) for character in sentence)
        return json.dumps(
            {
                "type": "cipher",
                "sentence": sentence,
                "encoded": encoded,
                "mapping": [
                    {"symbol": mapping[letter], "letter": letter} for letter in letters
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def render(
        self,
        settings: Settings,
        content_id: int | str,
        rect: Rect,
        now: datetime,
    ) -> Image.Image:
        del now
        if not isinstance(content_id, str):
            raise ConfigError("invalid language snapshot")
        try:
            snapshot = json.loads(content_id)
            encoded = snapshot["encoded"]
            mapping = snapshot["mapping"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ConfigError("invalid language snapshot") from exc
        if (
            snapshot.get("type") != "cipher"
            or not isinstance(encoded, str)
            or not encoded
            or not isinstance(mapping, list)
            or len(mapping) not in {2, 3}
            or not all(
                isinstance(item, dict)
                and item.get("symbol") in SYMBOLS
                and isinstance(item.get("letter"), str)
                and len(item["letter"]) == 1
                for item in mapping
            )
        ):
            raise ConfigError("invalid language snapshot")

        image = Image.new("L", (rect.width, rect.height), 255)
        draw = ImageDraw.Draw(image)
        title_size = 26 if rect.width >= 500 else 18
        title_font = ImageFont.truetype(str(settings.font), title_size)
        draw.text(
            (rect.width / 2, 4),
            "字母密码：破解句子",
            font=title_font,
            fill=0,
            anchor="ma",
        )

        clue_height = 38
        content_top = title_size + 16
        max_height = rect.height - content_top - clue_height
        sentence_font, lines = self._fit_sentence(
            draw,
            encoded,
            settings.font,
            rect.width - 32,
            max_height,
        )
        spacing = max(3, sentence_font.size // 5)
        text = "\n".join(lines)
        draw.multiline_text(
            (rect.width / 2, content_top + max_height / 2),
            text,
            font=sentence_font,
            fill=0,
            spacing=spacing,
            align="center",
            anchor="mm",
        )
        clue_font = ImageFont.truetype(str(settings.font), 24 if rect.width >= 500 else 18)
        clues = "    ".join(f"{item['symbol']} = ?" for item in mapping)
        draw.text(
            (rect.width / 2, rect.height - 6),
            clues,
            font=clue_font,
            fill=0,
            anchor="md",
        )
        return image.point(lambda pixel: 255 if pixel > 180 else 0, mode="1")

    @staticmethod
    def _fit_sentence(
        draw: ImageDraw.ImageDraw,
        sentence: str,
        font_path: Path,
        max_width: int,
        max_height: int,
    ) -> tuple[ImageFont.FreeTypeFont, list[str]]:
        for size in range(min(48, max_height), 17, -3):
            font = ImageFont.truetype(str(font_path), size)
            lines: list[str] = []
            current = ""
            for word in sentence.split():
                candidate = word if not current else f"{current} {word}"
                if current and draw.textlength(candidate, font=font) > max_width:
                    lines.append(current)
                    current = word
                else:
                    current = candidate
            if current:
                lines.append(current)
            spacing = max(3, size // 5)
            bounds = draw.multiline_textbbox(
                (0, 0),
                "\n".join(lines),
                font=font,
                spacing=spacing,
            )
            if bounds[3] - bounds[1] <= max_height:
                return font, lines
        return ImageFont.truetype(str(font_path), 18), [sentence]
