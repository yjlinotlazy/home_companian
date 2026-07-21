from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
import json
from pathlib import Path
import random
from threading import Lock

from PIL import Image, ImageDraw, ImageFont

from ..config import ConfigError, Settings
from ..domain import Rect, SlotAssignment


PROBLEM_TYPES = {
    "arithmetic": "算术",
    "thinking": "数学思维",
    "game24": "24点",
}
STORED_PROBLEM_TYPES = {"arithmetic", "thinking"}
GAME24_FACTORS = {1, 2, 3}


@dataclass(frozen=True)
class MathProblem:
    id: int
    type: str
    question: str
    answer: str


def load_math_problems(library_dir: Path) -> tuple[MathProblem, ...]:
    path = library_dir / "math" / "problems.csv"
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"id", "type", "question", "answer"}
            if reader.fieldnames is None or set(reader.fieldnames) != required:
                raise ConfigError(
                    "math/problems.csv must use id,type,question,answer"
                )
            problems: list[MathProblem] = []
            seen: set[int] = set()
            for line_number, row in enumerate(reader, 2):
                try:
                    problem_id = int(row["id"])
                except (TypeError, ValueError) as exc:
                    raise ConfigError(
                        f"math/problems.csv line {line_number} has invalid id"
                    ) from exc
                problem_type = row["type"].strip()
                question = row["question"].strip()
                answer = row["answer"].strip()
                if (
                    problem_id <= 0
                    or problem_id in seen
                    or problem_type not in STORED_PROBLEM_TYPES
                    or not question
                    or not answer
                ):
                    raise ConfigError(
                        f"math/problems.csv line {line_number} is invalid"
                    )
                seen.add(problem_id)
                problems.append(MathProblem(problem_id, problem_type, question, answer))
    except OSError as exc:
        raise ConfigError(f"math problem file cannot be opened: {path}") from exc
    if not problems:
        raise ConfigError("math/problems.csv must contain at least one problem")
    return tuple(problems)


@lru_cache(maxsize=512)
def solve_game24(numbers: tuple[int, ...]) -> str | None:
    """Return an integer-only +, -, × solution using every number once."""

    if len(numbers) != 4 or any(type(number) is not int or not 1 <= number <= 9 for number in numbers):
        return None

    def search(values: tuple[tuple[int, str], ...]) -> str | None:
        if len(values) == 1:
            return values[0][1] if values[0][0] == 24 else None
        for left_index in range(len(values)):
            for right_index in range(left_index + 1, len(values)):
                left_value, left_text = values[left_index]
                right_value, right_text = values[right_index]
                remaining = tuple(
                    value
                    for index, value in enumerate(values)
                    if index not in {left_index, right_index}
                )
                candidates = [
                    (left_value + right_value, f"({left_text} + {right_text})"),
                ]
                if left_value >= right_value:
                    candidates.append(
                        (left_value - right_value, f"({left_text} - {right_text})")
                    )
                else:
                    candidates.append(
                        (right_value - left_value, f"({right_text} - {left_text})")
                    )
                if left_value in GAME24_FACTORS or right_value in GAME24_FACTORS:
                    candidates.append(
                        (left_value * right_value, f"({left_text} × {right_text})")
                    )
                for value, text in candidates:
                    if not 0 <= value <= 100:
                        continue
                    answer = search(remaining + ((value, text),))
                    if answer is not None:
                        return answer
        return None

    return search(tuple((number, str(number)) for number in numbers))


class MathModule:
    name = "math"

    def __init__(self) -> None:
        self._last_id: int | None = None
        self._last_game24: tuple[int, ...] | None = None
        self._lock = Lock()

    def prepare(
        self,
        settings: Settings,
        at: datetime,
        assignment: SlotAssignment,
    ) -> int | str:
        del at
        selected_type = assignment.option("type", "all")
        if selected_type not in {*PROBLEM_TYPES, "all"}:
            raise ConfigError(
                "math module type must be arithmetic, thinking, game24, or all"
            )
        if selected_type == "game24":
            return self._prepare_game24()
        if selected_type == "all" and random.choice((False, False, True)):
            return self._prepare_game24()
        problems = tuple(
            problem
            for problem in load_math_problems(settings.library_dir)
            if selected_type == "all" or problem.type == selected_type
        )
        if not problems:
            raise ConfigError(f"math problem pool is empty for type: {selected_type}")
        with self._lock:
            candidates = tuple(
                problem
                for problem in problems
                if len(problems) == 1 or problem.id != self._last_id
            )
            selected = random.choice(candidates)
            self._last_id = selected.id
            return selected.id

    def render(
        self,
        settings: Settings,
        content_id: int | str,
        rect: Rect,
        now: datetime,
    ) -> Image.Image:
        del now
        if isinstance(content_id, str):
            try:
                snapshot = json.loads(content_id)
                numbers = snapshot["numbers"]
                answer = snapshot["answer"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ConfigError(f"invalid math content id: {content_id}") from exc
            if (
                snapshot.get("type") != "game24"
                or not isinstance(numbers, list)
                or len(numbers) != 4
                or not all(type(number) is int and 1 <= number <= 9 for number in numbers)
                or not isinstance(answer, str)
                or not answer
            ):
                raise ConfigError(f"invalid math content id: {content_id}")
            image = Image.new("L", (rect.width, rect.height), 255)
            draw = ImageDraw.Draw(image)
            return self._render_game24(
                draw,
                image,
                " ".join(str(number) for number in numbers),
                settings,
                rect,
            )
        if type(content_id) is not int:
            raise ConfigError(f"invalid math content id: {content_id}")
        problem = next(
            (
                candidate
                for candidate in load_math_problems(settings.library_dir)
                if candidate.id == content_id
            ),
            None,
        )
        if problem is None:
            raise ConfigError(f"unknown math problem id: {content_id}")

        image = Image.new("L", (rect.width, rect.height), 255)
        draw = ImageDraw.Draw(image)
        if problem.type == "game24":
            return self._render_game24(draw, image, problem.question, settings, rect)

        label_font = ImageFont.truetype(str(settings.font), 18 if rect.width >= 300 else 14)
        draw.text((12, 8), PROBLEM_TYPES[problem.type], font=label_font, fill=0)
        max_width = rect.width - 32
        max_height = rect.height - 48
        question_font, lines = self._fit_question(
            draw,
            problem.question,
            settings.font,
            max_width,
            max_height,
        )
        spacing = max(2, question_font.size // 5)
        bounds = draw.multiline_textbbox(
            (0, 0), "\n".join(lines), font=question_font, spacing=spacing, align="center"
        )
        text_width = bounds[2] - bounds[0]
        text_height = bounds[3] - bounds[1]
        x = (rect.width - text_width) / 2 - bounds[0]
        y = 38 + (max_height - text_height) / 2 - bounds[1]
        draw.multiline_text(
            (x, y),
            "\n".join(lines),
            font=question_font,
            fill=0,
            spacing=spacing,
            align="center",
        )
        return image.point(lambda pixel: 255 if pixel > 180 else 0, mode="1")

    def _prepare_game24(self) -> str:
        with self._lock:
            for _ in range(2000):
                numbers = tuple(sorted(random.randint(1, 9) for _ in range(4)))
                if numbers == self._last_game24 or self._boring_game24(numbers):
                    continue
                answer = solve_game24(numbers)
                if answer is None:
                    continue
                shown = list(numbers)
                random.shuffle(shown)
                self._last_game24 = numbers
                return json.dumps(
                    {"type": "game24", "numbers": shown, "answer": answer},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
        raise ConfigError("could not generate a solvable 24-point game")

    @staticmethod
    def _boring_game24(numbers: tuple[int, ...]) -> bool:
        unique = sorted(set(numbers))
        return len(unique) == 1 or (
            len(unique) == 4
            and unique[-1] - unique[0] == 3
            and all(right - left == 1 for left, right in zip(unique, unique[1:]))
        )

    @staticmethod
    def _render_game24(
        draw: ImageDraw.ImageDraw,
        image: Image.Image,
        question: str,
        settings: Settings,
        rect: Rect,
    ) -> Image.Image:
        numbers = question.split()
        if len(numbers) != 4 or any(not number.isdigit() for number in numbers):
            raise ConfigError("game24 question must contain four space-separated numbers")

        columns = 4 if rect.width >= 400 else 2
        rows = 1 if columns == 4 else 2
        title_size = 28 if rect.width >= 300 else 18
        title_font = ImageFont.truetype(str(settings.font), title_size)
        draw.text((rect.width / 2, 4), "24点", font=title_font, fill=0, anchor="ma")
        content_top = title_size + 14
        cell_width = rect.width / columns
        cell_height = (rect.height - content_top) / rows
        font_size = int(min(cell_width * 0.58, cell_height * 0.62, 96))
        font = ImageFont.truetype(str(settings.latin_font), max(28, font_size))
        for index, number in enumerate(numbers):
            column = index % columns
            row = index // columns
            x = column * cell_width + cell_width / 2
            y = content_top + row * cell_height + cell_height / 2
            draw.text((x, y), number, font=font, fill=0, anchor="mm")
        return image.point(lambda pixel: 255 if pixel > 180 else 0, mode="1")

    @staticmethod
    def _fit_question(
        draw: ImageDraw.ImageDraw,
        text: str,
        font_path: Path,
        max_width: int,
        max_height: int,
    ) -> tuple[ImageFont.FreeTypeFont, list[str]]:
        for size in range(min(58, max_height), 17, -4):
            font = ImageFont.truetype(str(font_path), size)
            lines: list[str] = []
            current = ""
            for character in text:
                candidate = current + character
                if current and draw.textlength(candidate, font=font) > max_width:
                    lines.append(current)
                    current = character
                else:
                    current = candidate
            if current:
                lines.append(current)
            spacing = max(2, size // 5)
            bounds = draw.multiline_textbbox(
                (0, 0), "\n".join(lines), font=font, spacing=spacing
            )
            if bounds[3] - bounds[1] <= max_height:
                return font, lines
        font = ImageFont.truetype(str(font_path), 18)
        return font, [text]
