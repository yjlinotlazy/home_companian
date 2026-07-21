from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path, PurePosixPath

from PIL import Image, ImageDraw, ImageFont, ImageOps

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
        configured_group = next(
            (candidate for candidate in settings.checklist_groups if candidate.id == group),
            None,
        )
        if configured_group is None:
            raise ConfigError(f"unknown checklist group: {group}")
        store = ChecklistStore(settings.library_dir)
        available_ids = {item.id for item in store.items()}
        unknown_ids = set(configured_group.item_ids) - available_ids
        if unknown_ids:
            raise ConfigError(
                f"checklist group {group} references unknown item: {min(unknown_ids)}"
            )
        group_ids = set(configured_group.item_ids)
        completed_ids = sorted(store.completed_ids(at.date()) & group_ids)
        portrait = assignment.option("portrait")
        portrait_width = 190
        if portrait is not None:
            self._portrait_path(settings.library_dir, portrait)
            raw_portrait_width = assignment.option("portrait_width")
            if raw_portrait_width is not None:
                try:
                    portrait_width = int(raw_portrait_width)
                except ValueError as exc:
                    raise ConfigError("checklist portrait_width must be an integer") from exc
                if not 40 <= portrait_width <= 190:
                    raise ConfigError(
                        "checklist portrait_width must be between 40 and 190"
                    )
        reward_snapshot = None
        reward_id = assignment.option("reward")
        if reward_id is not None:
            if reward_id != settings.reward.id:
                raise ConfigError(f"unknown reward: {reward_id}")
            reward_snapshot = {
                "id": settings.reward.id,
                "name": settings.reward.name,
                "cost": settings.reward.cost,
                "score": store.reward_score(settings.reward, at),
            }
        return json.dumps(
            {
                "group": group,
                "item_ids": list(configured_group.item_ids),
                "date": at.date().isoformat(),
                "completed": completed_ids,
                "portrait": portrait,
                "portrait_width": portrait_width,
                "reward": reward_snapshot,
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
            item_ids = snapshot["item_ids"]
            completed_ids = frozenset(snapshot["completed"])
            portrait = snapshot.get("portrait")
            portrait_width = snapshot.get("portrait_width", 190)
            reward = snapshot.get("reward")
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ConfigError("invalid checklist snapshot") from exc
        if not isinstance(group, str) or (
            portrait is not None and not isinstance(portrait, str)
        ) or type(portrait_width) is not int or not 40 <= portrait_width <= 190 or not isinstance(item_ids, list) or not all(
            type(item_id) is int for item_id in item_ids
        ) or not all(
            type(item_id) is int for item_id in completed_ids
        ):
            raise ConfigError("invalid checklist snapshot")
        if reward is not None and (
            not isinstance(reward, dict)
            or not isinstance(reward.get("name"), str)
            or type(reward.get("cost")) is not int
            or type(reward.get("score")) is not int
            or reward["cost"] <= 0
            or not 0 <= reward["score"] <= reward["cost"]
        ):
            raise ConfigError("invalid checklist reward snapshot")
        store = ChecklistStore(settings.library_dir)
        items_by_id = {item.id: item for item in store.items()}
        try:
            items = tuple(items_by_id[item_id] for item_id in item_ids)
        except KeyError as exc:
            raise ConfigError(
                f"checklist group {group} references unknown item: {exc.args[0]}"
            ) from exc
        del now

        image = Image.new("L", (rect.width, rect.height), 255)
        draw = ImageDraw.Draw(image)
        title_font = ImageFont.truetype(str(settings.font), 36)
        reward_height = 62 if reward is not None else 0
        content_height = rect.height - reward_height
        text_size = min(
            32,
            max(20, (content_height - 70) // max(1, len(items)) - 8),
        )
        chinese_font = ImageFont.truetype(str(settings.font), text_size)
        latin_font = ImageFont.truetype(str(settings.latin_font), text_size)

        if portrait is None:
            title_box = draw.textbbox((0, 0), group, font=title_font)
            title_width = title_box[2] - title_box[0]
            draw.text(((rect.width - title_width) / 2, 12), group, font=title_font, fill=0)
        else:
            portrait_path = self._portrait_path(settings.library_dir, portrait)
            try:
                with Image.open(portrait_path) as source:
                    rgba = source.convert("RGBA")
                    white = Image.new("RGBA", rgba.size, "white")
                    white.alpha_composite(rgba)
                    rendered_portrait = ImageOps.contain(
                        white.convert("L"),
                        (min(portrait_width, rect.width // 2), max(1, content_height - 20)),
                        Image.Resampling.LANCZOS,
                    )
            except OSError as exc:
                raise ConfigError(
                    f"checklist portrait cannot be opened: {portrait_path}"
                ) from exc
            portrait_x = rect.width - rendered_portrait.width - 8
            portrait_y = 8
            image.paste(rendered_portrait, (portrait_x, portrait_y))

        box_size = max(18, text_size - 3)
        line_height = max(box_size + 12, text_size + 12)
        y = 64
        for item in items:
            if y + line_height > content_height:
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
        if reward is not None:
            reward_font = ImageFont.truetype(str(settings.font), 36)
            label = reward["name"]
            label_box = draw.textbbox((0, 0), label, font=reward_font)
            label_width = label_box[2] - label_box[0]
            center_y = rect.height - 30
            draw.text((22, center_y), label, font=reward_font, fill=0, anchor="lm")
            bar_x = 22 + label_width + 16
            bar_right = rect.width - 22
            bar_top = center_y - 11
            bar_bottom = center_y + 11
            draw.rectangle(
                (bar_x, bar_top, bar_right, bar_bottom),
                outline=0,
                width=3,
            )
            inner_width = max(0, bar_right - bar_x - 6)
            filled_width = round(inner_width * reward["score"] / reward["cost"])
            if filled_width > 0:
                draw.rectangle(
                    (bar_x + 3, bar_top + 3, bar_x + 3 + filled_width, bar_bottom - 3),
                    fill=0,
                )
        return image.point(lambda pixel: 255 if pixel > 180 else 0, mode="1")

    @staticmethod
    def _portrait_path(library_dir: Path, content_id: str) -> Path:
        relative = PurePosixPath(content_id)
        if (
            relative.is_absolute()
            or len(relative.parts) != 2
            or relative.parts[0] != "portraits"
            or any(part in {".", ".."} for part in relative.parts)
            or Path(relative.parts[1]).suffix.lower() != ".png"
        ):
            raise ConfigError(f"invalid checklist portrait: {content_id}")
        path = library_dir / relative.parts[0] / relative.parts[1]
        if not path.is_file():
            raise ConfigError(f"checklist portrait cannot be opened: {path}")
        return path

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
