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
            self._dice_count_up,
            self._dice_count_down,
            self._dice_alternating,
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
        text_items = [item for item in shown if not item.startswith("die:")]
        font = self._fit_font(
            draw,
            text_items,
            font_path,
            cell_width - 10,
            cell_height - 10,
        )
        for index, item in enumerate(shown):
            left = 12 + index * (cell_width + gap)
            top = content_top
            right = left + cell_width
            bottom = top + cell_height
            draw.rounded_rectangle((left, top, right, bottom), radius=8, outline=0, width=2)
            if item.startswith("die:"):
                try:
                    die_value = int(item.removeprefix("die:"))
                except ValueError as exc:
                    raise ConfigError("invalid die value") from exc
                self._draw_die(draw, die_value, left, top, right, bottom)
            else:
                draw.text(
                    ((left + right) / 2, (top + bottom) / 2),
                    item,
                    font=font,
                    fill=0,
                    anchor="mm",
                )
        return image.point(lambda pixel: 255 if pixel > 180 else 0, mode="1")

    @staticmethod
    def _draw_die(
        draw: ImageDraw.ImageDraw,
        value: int,
        left: float,
        top: float,
        right: float,
        bottom: float,
    ) -> None:
        if not 1 <= value <= 6:
            raise ConfigError("invalid die value")
        side = min(right - left - 12, bottom - top - 12)
        die_left = (left + right - side) / 2
        die_top = (top + bottom - side) / 2
        die_right = die_left + side
        die_bottom = die_top + side
        draw.rounded_rectangle(
            (die_left, die_top, die_right, die_bottom),
            radius=max(4, int(side // 7)),
            outline=0,
            width=max(2, int(side // 22)),
        )
        positions = {
            "tl": (0.27, 0.27),
            "tc": (0.5, 0.27),
            "tr": (0.73, 0.27),
            "ml": (0.27, 0.5),
            "mc": (0.5, 0.5),
            "mr": (0.73, 0.5),
            "bl": (0.27, 0.73),
            "bc": (0.5, 0.73),
            "br": (0.73, 0.73),
        }
        layouts = {
            1: ("mc",),
            2: ("tl", "br"),
            3: ("tl", "mc", "br"),
            4: ("tl", "tr", "bl", "br"),
            5: ("tl", "tr", "mc", "bl", "br"),
            6: ("tl", "tr", "ml", "mr", "bl", "br"),
        }
        radius = max(2, int(side // 13))
        for name in layouts[value]:
            x_ratio, y_ratio = positions[name]
            x = die_left + side * x_ratio
            y = die_top + side * y_ratio
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=0)

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

    @staticmethod
    def _dice_count_up() -> tuple[str, tuple[str, ...]]:
        return "dice_up", tuple(f"die:{value}" for value in range(1, 7))

    @staticmethod
    def _dice_count_down() -> tuple[str, tuple[str, ...]]:
        return "dice_down", tuple(f"die:{value}" for value in range(6, 0, -1))

    @staticmethod
    def _dice_alternating() -> tuple[str, tuple[str, ...]]:
        left, right = random.sample(range(1, 7), 2)
        return "dice_alternating", tuple(
            f"die:{(left, right)[index % 2]}" for index in range(6)
        )
