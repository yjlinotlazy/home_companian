from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import math

from PIL import Image

from ..config import ConfigError, Settings
from ..domain import StatusAssignment
from .text import render_text


SOLAR_TERMS = (
    "小寒", "大寒", "立春", "雨水", "惊蛰", "春分",
    "清明", "谷雨", "立夏", "小满", "芒种", "夏至",
    "小暑", "大暑", "立秋", "处暑", "白露", "秋分",
    "寒露", "霜降", "立冬", "小雪", "大雪", "冬至",
)
CHINA_TIME = timezone(timedelta(hours=8))


def _sun_apparent_longitude(at: datetime) -> float:
    julian_day = at.timestamp() / 86400 + 2440587.5
    centuries = (julian_day - 2451545.0) / 36525
    mean_longitude = (
        280.46646 + centuries * (36000.76983 + centuries * 0.0003032)
    ) % 360
    mean_anomaly = math.radians(
        357.52911 + centuries * (35999.05029 - 0.0001537 * centuries)
    )
    equation = (
        math.sin(mean_anomaly)
        * (1.914602 - centuries * (0.004817 + 0.000014 * centuries))
        + math.sin(2 * mean_anomaly) * (0.019993 - 0.000101 * centuries)
        + math.sin(3 * mean_anomaly) * 0.000289
    )
    omega = math.radians(125.04 - 1934.136 * centuries)
    return (mean_longitude + equation - 0.00569 - 0.00478 * math.sin(omega)) % 360


def _term_index(at: datetime) -> int:
    return int(((_sun_apparent_longitude(at) - 285) % 360) // 15)


@lru_cache(maxsize=16)
def _solar_term_dates(year: int) -> tuple[date, ...]:
    if not 1900 <= year <= 2100:
        raise ConfigError("solar_term supports years 1900 through 2100")
    starts: dict[int, datetime] = {}
    cursor = datetime(year - 1, 12, 15, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 15, tzinfo=timezone.utc)
    previous_index = _term_index(cursor)
    while cursor < end:
        following = cursor + timedelta(hours=6)
        following_index = _term_index(following)
        if following_index != previous_index:
            low, high = cursor, following
            for _ in range(20):
                middle = low + (high - low) / 2
                if _term_index(middle) == previous_index:
                    low = middle
                else:
                    high = middle
            if high.astimezone(CHINA_TIME).year == year:
                starts[following_index] = high
        cursor = following
        previous_index = following_index
    if len(starts) != len(SOLAR_TERMS):
        raise ConfigError(f"could not calculate all solar terms for {year}")
    return tuple(starts[index].astimezone(CHINA_TIME).date() for index in range(24))


def solar_term_date(year: int, index: int) -> date:
    return _solar_term_dates(year)[index]


def current_solar_term(at: date) -> str:
    candidates = [
        (solar_term_date(year, index), name)
        for year in (at.year - 1, at.year)
        for index, name in enumerate(SOLAR_TERMS)
    ]
    return max(candidate for candidate in candidates if candidate[0] <= at)[1]


class SolarTermModule:
    name = "solar_term"

    def render(
        self,
        settings: Settings,
        at: datetime,
        assignment: StatusAssignment,
    ) -> Image.Image:
        if assignment.options:
            raise ConfigError("solar_term module does not accept options")
        return render_text(current_solar_term(at.date()), settings.font)
