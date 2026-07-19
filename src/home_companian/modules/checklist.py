from __future__ import annotations

from datetime import datetime
import json

from PIL import Image, ImageDraw, ImageFont

from ..checklists import ChecklistStore
from ..config import ConfigError, Settings
from ..domain import Rect, SlotAssignment


class ChecklistModule:
    name = "checklist"

    def prepare(
        self,
        settings: Settings,
        at: datetime,
        assignment: SlotAssignment,
    ) -> str:
        group = assignment.option("group")
        if group is None:
            raise ConfigError("checklist module requires group")
        store = ChecklistStore(settings.library_dir)
        group_ids = {
            item.id for item in store.items() if item.group == group
        }
        if not group_ids:
            raise ConfigError(f"unknown checklist group: {group}")
        completed_ids = sorted(store.completed_ids(at.date()) & group_ids)
        return json.dumps(
            {
                "group": group,
                "date": at.date().isoformat(),
                "completed": completed_ids,
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
        if not isinstance(content_id, str):
            raise ConfigError(f"invalid checklist snapshot: {content_id}")
        try:
            snapshot = json.loads(content_id)
            group = snapshot["group"]
            completed_ids = frozenset(snapshot["completed"])
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ConfigError("invalid checklist snapshot") from exc
        if not isinstance(group, str) or not all(
            type(item_id) is int for item_id in completed_ids
        ):
            raise ConfigError("invalid checklist snapshot")
        store = ChecklistStore(settings.library_dir)
        items = tuple(item for item in store.items() if item.group == group)
        if not items:
            raise ConfigError(f"unknown checklist group: {group}")
        del now

        image = Image.new("L", (rect.width, rect.height), 255)
        draw = ImageDraw.Draw(image)
        title_font = ImageFont.truetype(str(settings.font), 36)
        text_size = min(32, max(20, (rect.height - 70) // max(1, len(items)) - 8))
        chinese_font = ImageFont.truetype(str(settings.font), text_size)
        latin_font = ImageFont.truetype(str(settings.latin_font), text_size)

        title_box = draw.textbbox((0, 0), group, font=title_font)
        title_width = title_box[2] - title_box[0]
        draw.text(((rect.width - title_width) / 2, 12), group, font=title_font, fill=0)

        box_size = max(18, text_size - 3)
        line_height = max(box_size + 12, text_size + 12)
        y = 64
        for item in items:
            if y + line_height > rect.height:
                break
            box_y = y + (line_height - box_size) // 2
            draw.rectangle(
                (22, box_y, 22 + box_size, box_y + box_size),
                outline=0,
                width=3,
            )
            if item.id in completed_ids:
                inset = 5
                draw.line(
                    (
                        22 + inset,
                        box_y + box_size // 2,
                        22 + box_size // 2,
                        box_y + box_size - inset,
                    ),
                    fill=0,
                    width=3,
                )
                draw.line(
                    (
                        22 + box_size // 2,
                        box_y + box_size - inset,
                        22 + box_size - inset,
                        box_y + inset,
                    ),
                    fill=0,
                    width=3,
                )
            self._draw_mixed_text(
                draw,
                item.text,
                (22 + box_size + 14, y + line_height // 2),
                chinese_font,
                latin_font,
            )
            y += line_height
        return image.point(lambda pixel: 255 if pixel > 180 else 0, mode="1")

    @staticmethod
    def _draw_mixed_text(
        draw: ImageDraw.ImageDraw,
        text: str,
        position: tuple[int, int],
        chinese_font: ImageFont.FreeTypeFont,
        latin_font: ImageFont.FreeTypeFont,
    ) -> None:
        x, center_y = position
        for character in text:
            font = chinese_font if ord(character) > 127 else latin_font
            bounds = draw.textbbox((0, 0), character, font=font, anchor="lm")
            draw.text((x, center_y), character, font=font, fill=0, anchor="lm")
            x += bounds[2] - bounds[0]
