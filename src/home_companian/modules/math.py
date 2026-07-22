from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import random
from threading import Lock

from PIL import Image, ImageDraw, ImageFont

from ..config import ConfigError, Settings
from ..domain import Rect, SlotAssignment
from .math_games import Game24, MathGame, PatternGame, solve_game24


PROBLEM_TYPES = {
    "arithmetic": "算术",
    "thinking": "数学思维",
    "game24": "24点",
    "pattern": "找规律",
}
STORED_PROBLEM_TYPES = {"arithmetic", "thinking"}
GENERATED_GROUP = "games"


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


class MathModule:
    name = "math"

    def __init__(self) -> None:
        self._last_id: int | None = None
        games: tuple[MathGame, ...] = (Game24(), PatternGame())
        self._games = {game.type: game for game in games}
        self._last_game_type: str | None = None
        self._lock = Lock()

    def prepare(
        self,
        settings: Settings,
        at: datetime,
        assignment: SlotAssignment,
    ) -> int | str:
        del at
        selected_type = assignment.option("type", "all")
        if selected_type not in {*PROBLEM_TYPES, GENERATED_GROUP, "all"}:
            raise ConfigError(
                "math module type must be arithmetic, thinking, game24, pattern, "
                "games, or all"
            )
        if selected_type in self._games:
            return self._prepare_game(selected_type)
        if selected_type == GENERATED_GROUP:
            return self._prepare_game()
        if selected_type == "all" and random.choice((False, False, True)):
            return self._prepare_game()
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
            except (json.JSONDecodeError, TypeError) as exc:
                raise ConfigError(f"invalid math content id: {content_id}") from exc
            if not isinstance(snapshot, dict):
                raise ConfigError(f"invalid math content id: {content_id}")
            game = self._games.get(snapshot.get("type"))
            if game is None:
                raise ConfigError(f"invalid math content id: {content_id}")
            try:
                return game.render(snapshot, settings, rect)
            except ConfigError as exc:
                raise ConfigError(f"invalid math content id: {content_id}") from exc
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

    def _prepare_game(self, selected_type: str | None = None) -> str:
        with self._lock:
            if selected_type is None:
                candidates = tuple(
                    game_type
                    for game_type in self._games
                    if len(self._games) == 1 or game_type != self._last_game_type
                )
                selected_type = random.choice(candidates)
            game = self._games[selected_type]
            self._last_game_type = selected_type
        return json.dumps(
            game.prepare(),
            ensure_ascii=False,
            separators=(",", ":"),
        )

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
