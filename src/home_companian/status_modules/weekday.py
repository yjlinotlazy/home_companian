from datetime import datetime

from PIL import Image

from ..config import Settings
from ..domain import StatusAssignment
from .text import render_text


class WeekdayModule:
    name = "weekday"

    def render(
        self,
        settings: Settings,
        at: datetime,
        assignment: StatusAssignment,
    ) -> Image.Image:
        del assignment
        weekdays = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
        return render_text(weekdays[at.weekday()], settings.font)
