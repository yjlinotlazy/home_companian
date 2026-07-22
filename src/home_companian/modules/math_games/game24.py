from __future__ import annotations

from functools import lru_cache
import random
from threading import Lock

from PIL import Image, ImageDraw, ImageFont

from ...config import ConfigError, Settings
from ...domain import Rect


GAME24_FACTORS = {1, 2, 3}


@lru_cache(maxsize=512)
def solve_game24(numbers: tuple[int, ...]) -> str | None:
    """Return an integer-only +, -, × solution using every number once."""

    if len(numbers) != 4 or any(
        type(number) is not int or not 1 <= number <= 9 for number in numbers
    ):
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
                candidates = [(left_value + right_value, f"({left_text} + {right_text})")]
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


class Game24:
    type = "game24"

    def __init__(self) -> None:
        self._last_numbers: tuple[int, ...] | None = None
        self._lock = Lock()

    def prepare(self) -> dict[str, object]:
        with self._lock:
            for _ in range(2000):
                numbers = tuple(sorted(random.randint(1, 9) for _ in range(4)))
                if numbers == self._last_numbers or self._boring(numbers):
                    continue
                answer = solve_game24(numbers)
                if answer is None:
                    continue
                shown = list(numbers)
                random.shuffle(shown)
                self._last_numbers = numbers
                return {"type": self.type, "numbers": shown, "answer": answer}
        raise ConfigError("could not generate a solvable 24-point game")

    def render(
        self,
        snapshot: dict[str, object],
        settings: Settings,
        rect: Rect,
    ) -> Image.Image:
        numbers = snapshot.get("numbers")
        answer = snapshot.get("answer")
        if (
            snapshot.get("type") != self.type
            or not isinstance(numbers, list)
            or len(numbers) != 4
            or not all(type(number) is int and 1 <= number <= 9 for number in numbers)
            or not isinstance(answer, str)
            or not answer
        ):
            raise ConfigError("invalid game24 snapshot")

        image = Image.new("L", (rect.width, rect.height), 255)
        draw = ImageDraw.Draw(image)
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
            draw.text((x, y), str(number), font=font, fill=0, anchor="mm")
        return image.point(lambda pixel: 255 if pixel > 180 else 0, mode="1")

    @staticmethod
    def _boring(numbers: tuple[int, ...]) -> bool:
        unique = sorted(set(numbers))
        return len(unique) == 1 or (
            len(unique) == 4
            and unique[-1] - unique[0] == 3
            and all(right - left == 1 for left, right in zip(unique, unique[1:]))
        )
