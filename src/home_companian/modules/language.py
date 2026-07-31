from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
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
FILL_WORD_PART = re.compile(
    r"^(.*?)(?:（([^（）]+)）|\(([^()]+)\))(.*?)$"
)
SYMBOLS = ("△", "○", "□")
POEM_CLAUSE = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff]+$")


@dataclass(frozen=True)
class FillWordProblem:
    source: str
    answers: tuple[str, ...]
    prompts: tuple[str, ...]


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


def load_fill_word_problems(library_dir: Path) -> tuple[FillWordProblem, ...]:
    path = library_dir / "language" / "fill_words.txt"
    try:
        lines = tuple(
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    except OSError as exc:
        raise ConfigError(f"language fill-word file cannot be opened: {path}") from exc
    if not lines or len(set(lines)) != len(lines):
        raise ConfigError(f"{path} must contain unique problems")

    problems: list[FillWordProblem] = []
    for line_number, line in enumerate(lines, 1):
        parts = re.split(r"\s*[,，]\s*", line)
        answers: list[str] = []
        prompts: list[str] = []
        if len(parts) < 2:
            raise ConfigError(f"{path} line {line_number} is invalid")
        for part in parts:
            match = FILL_WORD_PART.fullmatch(part)
            if match is None:
                raise ConfigError(f"{path} line {line_number} is invalid")
            prefix, chinese_answer, english_answer, suffix = match.groups()
            answer = (chinese_answer or english_answer).strip()
            prefix = prefix.strip()
            suffix = suffix.strip()
            if (
                not answer
                or not (prefix or suffix)
                or any(character in "()（）,，" for character in answer + prefix + suffix)
            ):
                raise ConfigError(f"{path} line {line_number} is invalid")
            answers.append(answer)
            prompts.append(f"{prefix}__{suffix}")
        if len(set(answers)) != len(answers):
            raise ConfigError(f"{path} line {line_number} must use different choices")
        problems.append(FillWordProblem(line, tuple(answers), tuple(prompts)))
    return tuple(problems)


def load_chinese_poems(library_dir: Path) -> tuple[tuple[str, ...], ...]:
    path = library_dir / "language" / "chinese_poems.txt"
    try:
        lines = tuple(
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    except OSError as exc:
        raise ConfigError(f"Chinese poem file cannot be opened: {path}") from exc
    if not lines or len(set(lines)) != len(lines):
        raise ConfigError(f"{path} must contain unique poems")

    poems: list[tuple[str, ...]] = []
    for line_number, line in enumerate(lines, 1):
        clauses = tuple(
            clause.strip()
            for clause in re.split(r"[，,。.!！？?；;]+", line)
            if clause.strip()
        )
        if (
            len(clauses) != 4
            or any(POEM_CLAUSE.fullmatch(clause) is None for clause in clauses)
        ):
            raise ConfigError(
                f"{path} line {line_number} must contain four Chinese clauses"
            )
        poems.append(clauses)
    return tuple(poems)


class LanguageModule:
    name = "language"

    def __init__(self) -> None:
        self._last_sentence: str | None = None
        self._last_fill_problem: str | None = None
        self._last_poem: tuple[str, ...] | None = None
        self._last_game_type: str | None = None
        self._game_queue: list[str] = []
        self._lock = Lock()

    def prepare(
        self,
        settings: Settings,
        at: datetime,
        assignment: SlotAssignment,
    ) -> str:
        del at
        selected_type = assignment.option("type", "cipher")
        game_types = ("cipher", "fill_words", "chinese_poem")
        if selected_type not in {*game_types, "games"}:
            raise ConfigError(
                "language module type must be cipher, fill_words, "
                "chinese_poem, or games"
            )
        if selected_type == "games":
            with self._lock:
                if not self._game_queue:
                    self._game_queue = list(game_types)
                    random.shuffle(self._game_queue)
                    if (
                        self._last_game_type is not None
                        and self._game_queue[0] == self._last_game_type
                    ):
                        self._game_queue[0], self._game_queue[1] = (
                            self._game_queue[1],
                            self._game_queue[0],
                        )
                selected_type = self._game_queue.pop(0)
                self._last_game_type = selected_type
        else:
            with self._lock:
                self._game_queue = []
                self._last_game_type = selected_type
        if selected_type == "fill_words":
            return self._prepare_fill_words(settings)
        if selected_type == "chinese_poem":
            return self._prepare_chinese_poem(settings)

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

    def _prepare_chinese_poem(self, settings: Settings) -> str:
        poems = load_chinese_poems(settings.library_dir)
        with self._lock:
            candidates = tuple(
                poem
                for poem in poems
                if len(poems) == 1 or poem != self._last_poem
            )
            poem = random.choice(candidates)
            self._last_poem = poem
        return json.dumps(
            {
                "type": "chinese_poem",
                "clauses": list(poem),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def _prepare_fill_words(self, settings: Settings) -> str:
        problems = load_fill_word_problems(settings.library_dir)
        with self._lock:
            candidates = tuple(
                problem
                for problem in problems
                if len(problems) == 1 or problem.source != self._last_fill_problem
            )
            problem = random.choice(candidates)
            self._last_fill_problem = problem.source
        options = list(problem.answers)
        random.shuffle(options)
        return json.dumps(
            {
                "type": "fill_words",
                "options": options,
                "prompts": list(problem.prompts),
                "answers": list(problem.answers),
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
        except (json.JSONDecodeError, TypeError) as exc:
            raise ConfigError("invalid language snapshot") from exc
        if not isinstance(snapshot, dict):
            raise ConfigError("invalid language snapshot")
        if snapshot.get("type") == "fill_words":
            return self._render_fill_words(settings, snapshot, rect)
        if snapshot.get("type") == "chinese_poem":
            return self._render_chinese_poem(settings, snapshot, rect)
        try:
            encoded = snapshot["encoded"]
            mapping = snapshot["mapping"]
        except (KeyError, TypeError) as exc:
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
    def _render_chinese_poem(
        settings: Settings,
        snapshot: dict[str, object],
        rect: Rect,
    ) -> Image.Image:
        clauses = snapshot.get("clauses")
        if (
            not isinstance(clauses, list)
            or len(clauses) != 4
            or not all(
                isinstance(clause, str)
                and POEM_CLAUSE.fullmatch(clause) is not None
                for clause in clauses
            )
        ):
            raise ConfigError("invalid language snapshot")

        rows = (
            f"{clauses[0]}，{clauses[1]}。",
            f"{clauses[2]}，{clauses[3]}。",
        )
        image = Image.new("L", (rect.width, rect.height), 255)
        draw = ImageDraw.Draw(image)
        for size in range(min(68, rect.height // 3), 19, -3):
            font = ImageFont.truetype(str(settings.font), size)
            if all(
                draw.textlength(row, font=font) <= rect.width - 36
                for row in rows
            ):
                break
        else:
            font = ImageFont.truetype(str(settings.font), 20)
        for index, row in enumerate(rows):
            draw.text(
                (rect.width / 2, rect.height * (0.32 + index * 0.4)),
                row,
                font=font,
                fill=0,
                anchor="mm",
            )
        return image.point(lambda pixel: 255 if pixel > 180 else 0, mode="1")

    @staticmethod
    def _render_fill_words(
        settings: Settings,
        snapshot: dict[str, object],
        rect: Rect,
    ) -> Image.Image:
        options = snapshot.get("options")
        prompts = snapshot.get("prompts")
        answers = snapshot.get("answers")
        if (
            not isinstance(options, list)
            or len(options) < 2
            or not all(isinstance(value, str) and value for value in options)
            or len(set(options)) != len(options)
            or not isinstance(prompts, list)
            or len(prompts) != len(options)
            or not all(
                isinstance(value, str)
                and value.count("__") == 1
                and "(" not in value
                and ")" not in value
                and "（" not in value
                and "）" not in value
                for value in prompts
            )
            or not isinstance(answers, list)
            or len(answers) != len(options)
            or not all(isinstance(value, str) and value for value in answers)
            or sorted(options) != sorted(answers)
        ):
            raise ConfigError("invalid language snapshot")

        image = Image.new("L", (rect.width, rect.height), 255)
        draw = ImageDraw.Draw(image)
        values = [*options, *prompts]
        font_path = (
            settings.font
            if any(not value.isascii() for value in values)
            else settings.latin_font
        )
        cell_width = rect.width / len(prompts)
        for size in range(min(68, rect.height // 3), 19, -3):
            font = ImageFont.truetype(str(font_path), size)
            option_line = "    ".join(options)
            if (
                draw.textlength(option_line, font=font) <= rect.width - 32
                and all(
                    LanguageModule._fill_prompt_width(draw, prompt, font)
                    <= cell_width - 32
                    for prompt in prompts
                )
            ):
                break
        else:
            font = ImageFont.truetype(str(font_path), 20)

        draw.text(
            (rect.width / 2, rect.height * 0.30),
            "    ".join(options),
            font=font,
            fill=0,
            anchor="mm",
        )
        for index, prompt in enumerate(prompts):
            LanguageModule._draw_fill_prompt(
                draw,
                prompt,
                font=font,
                center_x=cell_width * (index + 0.5),
                center_y=rect.height * 0.72,
            )
        return image.point(lambda pixel: 255 if pixel > 180 else 0, mode="1")

    @staticmethod
    def _fill_prompt_width(
        draw: ImageDraw.ImageDraw,
        prompt: str,
        font: ImageFont.FreeTypeFont,
    ) -> float:
        prefix, suffix = prompt.split("__")
        return (
            draw.textlength(prefix, font=font)
            + font.size * 1.12
            + draw.textlength(suffix, font=font)
        )

    @staticmethod
    def _draw_fill_prompt(
        draw: ImageDraw.ImageDraw,
        prompt: str,
        font: ImageFont.FreeTypeFont,
        center_x: float,
        center_y: float,
    ) -> None:
        prefix, suffix = prompt.split("__")
        prefix_width = draw.textlength(prefix, font=font)
        blank_width = font.size * 1.12
        total_width = (
            prefix_width
            + blank_width
            + draw.textlength(suffix, font=font)
        )
        x = center_x - total_width / 2
        if prefix:
            draw.text((x, center_y), prefix, font=font, fill=0, anchor="lm")
        line_left = x + prefix_width
        line_y = center_y + font.size * 0.38
        draw.line(
            (line_left, line_y, line_left + blank_width, line_y),
            fill=0,
            width=max(2, font.size // 18),
        )
        if suffix:
            draw.text(
                (line_left + blank_width, center_y),
                suffix,
                font=font,
                fill=0,
                anchor="lm",
            )

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
