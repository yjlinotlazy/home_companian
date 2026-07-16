from datetime import datetime

from PIL import Image

from ..config import Settings
from ..domain import StatusAssignment
from .text import render_text


class DateModule:
    name = "date"

    def render(
        self,
        settings: Settings,
        at: datetime,
        assignment: StatusAssignment,
    ) -> Image.Image:
        return render_text(at.strftime(assignment.option("format", "%Y-%m-%d")), settings.latin_font)
