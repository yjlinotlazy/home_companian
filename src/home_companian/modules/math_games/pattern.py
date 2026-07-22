from __future__ import annotations

import random
from threading import Lock

from PIL import Image, ImageDraw, ImageFont

from ...config import ConfigError, Settings
from ...domain import Rect


SYMBOL_PAIRS = (("●", "○"), ("▲", "■"), ("◆", "○"), ("■", "●"))
SYMBOL_TRIPLES = (
    ("●", "▲", "■"),
    ("○", "△", "□"),
    ("★", "●", "▲"),
    ("+", "−", "×"),
)
DIRECTIONS = ("↑", "→", "↓", "←")
WORD_TRIPLES = (
    ("猫", "狗", "兔"),
    ("苹果", "梨", "桃"),
    ("春", "夏", "秋"),
)


class PatternGame:
    type = "pattern"

    def __init__(self) -> None:
        self._last_key: tuple[str, ...] | None = None
        self._lock = Lock()

    def prepare(self) -> dict[str, object]:
        generators = (
            self._count_up,
            self._count_down,
            self._alternating,
            self._repeat_symbols,
            self._repeat_symbol_triple,
            self._repeat_symbol_pair,
            self._rotate_directions,
            self._repeat_words,
            self._alternating_steps,
            self._growing_steps,
        )
        with self._lock:
            for _ in range(50):
                family, values = random.choice(generators)()
                key = (family, *values)
                if key == self._last_key:
                    continue
                self._last_key = key
                return {
                    "type": self.type,
                    "family": family,
                    "items": list(values[:5]),
                    "answer": values[5],
                }
        raise ConfigError("could not generate a pattern game")

    def render(
        self,
        snapshot: dict[str, object],
        settings: Settings,
        rect: Rect,
    ) -> Image.Image:
        items = snapshot.get("items")
        answer = snapshot.get("answer")
        family = snapshot.get("family")
        if (
            snapshot.get("type") != self.type
            or not isinstance(family, str)
            or not isinstance(items, list)
            or len(items) != 5
            or not all(isinstance(item, str) and item for item in items)
            or not isinstance(answer, str)
            or not answer
        ):
            raise ConfigError("invalid pattern snapshot")

        image = Image.new("L", (rect.width, rect.height), 255)
        draw = ImageDraw.Draw(image)
        title_size = 26 if rect.width >= 400 else 18
        title_font = ImageFont.truetype(str(settings.font), title_size)
        draw.text((rect.width / 2, 4), "找规律，填第六个", font=title_font, fill=0, anchor="ma")

        shown = [*items, "?"]
        content_top = title_size + 18
        gap = max(4, rect.width // 100)
        cell_width = (rect.width - 2 * 12 - 5 * gap) / 6
        cell_height = rect.height - content_top - 12
        font_path = settings.font if any(not item.isascii() for item in shown) else settings.latin_font
        font = self._fit_font(draw, shown, font_path, cell_width - 10, cell_height - 10)
        for index, item in enumerate(shown):
            left = 12 + index * (cell_width + gap)
            top = content_top
            right = left + cell_width
            bottom = top + cell_height
            draw.rounded_rectangle((left, top, right, bottom), radius=8, outline=0, width=2)
            draw.text(
                ((left + right) / 2, (top + bottom) / 2),
                item,
                font=font,
                fill=0,
                anchor="mm",
            )
        return image.point(lambda pixel: 255 if pixel > 180 else 0, mode="1")

    @staticmethod
    def _fit_font(
        draw: ImageDraw.ImageDraw,
        values: list[str],
        font_path: object,
        max_width: float,
        max_height: float,
    ) -> ImageFont.FreeTypeFont:
        for size in range(int(min(64, max_height * 0.64)), 15, -3):
            font = ImageFont.truetype(str(font_path), size)
            if all(
                (bounds := draw.textbbox((0, 0), value, font=font))[2] - bounds[0]
                <= max_width
                for value in values
            ):
                return font
        return ImageFont.truetype(str(font_path), 16)

    @staticmethod
    def _count_up() -> tuple[str, tuple[str, ...]]:
        step = random.randint(1, 5)
        start = random.randint(1, 30 - 5 * step)
        return "count_up", tuple(str(start + index * step) for index in range(6))

    @staticmethod
    def _count_down() -> tuple[str, tuple[str, ...]]:
        step = random.randint(1, 4)
        start = random.randint(5 * step + 1, 40)
        return "count_down", tuple(str(start - index * step) for index in range(6))

    @staticmethod
    def _alternating() -> tuple[str, tuple[str, ...]]:
        left = random.randint(1, 15)
        right = random.choice(tuple(value for value in range(1, 16) if value != left))
        return "alternating", tuple(str((left, right)[index % 2]) for index in range(6))

    @staticmethod
    def _repeat_symbols() -> tuple[str, tuple[str, ...]]:
        left, right = random.choice(SYMBOL_PAIRS)
        return "symbols", tuple((left, right)[index % 2] for index in range(6))

    @staticmethod
    def _repeat_symbol_triple() -> tuple[str, tuple[str, ...]]:
        values = random.choice(SYMBOL_TRIPLES)
        return "symbol_triple", tuple(values[index % 3] for index in range(6))

    @staticmethod
    def _repeat_symbol_pair() -> tuple[str, tuple[str, ...]]:
        left, right = random.choice(SYMBOL_PAIRS)
        pattern = (left, left, right)
        return "symbol_pair", tuple(pattern[index % 3] for index in range(6))

    @staticmethod
    def _rotate_directions() -> tuple[str, tuple[str, ...]]:
        start = random.randrange(len(DIRECTIONS))
        return "directions", tuple(
            DIRECTIONS[(start + index) % len(DIRECTIONS)] for index in range(6)
        )

    @staticmethod
    def _repeat_words() -> tuple[str, tuple[str, ...]]:
        values = random.choice(WORD_TRIPLES)
        return "words", tuple(values[index % 3] for index in range(6))

    @staticmethod
    def _alternating_steps() -> tuple[str, tuple[str, ...]]:
        start = random.randint(1, 8)
        first_step = random.randint(2, 4)
        second_step = random.randint(1, first_step - 1)
        values = [start]
        for index in range(5):
            values.append(values[-1] + (first_step if index % 2 == 0 else second_step))
        return "alternating_steps", tuple(str(value) for value in values)

    @staticmethod
    def _growing_steps() -> tuple[str, tuple[str, ...]]:
        start = random.randint(1, 5)
        values = [start]
        for step in range(1, 6):
            values.append(values[-1] + step)
        return "growing_steps", tuple(str(value) for value in values)
