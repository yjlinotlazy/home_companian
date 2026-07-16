from datetime import datetime

from PIL import Image

from ..config import Settings
from ..domain import StatusAssignment
from .text import render_text


class TimeModule:
    name = "time"

    def render(
        self,
        settings: Settings,
        at: datetime,
        assignment: StatusAssignment,
    ) -> Image.Image:
        return render_text(at.strftime(assignment.option("format", "%H:%M")), settings.latin_font)
