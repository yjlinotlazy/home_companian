from datetime import date, datetime
from pathlib import Path
import unittest

from home_companian.config import FontChoice, Item, ScheduleEntry, Settings
from home_companian.domain import (
    PanelConfig,
    SlotAssignment,
    StatusAssignment,
    StatusBarConfig,
)
from home_companian.status_bar import render_status_bar
from home_companian.status_modules import (
    DateModule,
    SolarTermModule,
    TimeModule,
    WeekdayModule,
)
from home_companian.status_modules.solar_term import current_solar_term


FONT = Path("/usr/share/fonts/adobe-source-han-sans/SourceHanSansCN-Regular.otf")


def settings(status_bar: StatusBarConfig) -> Settings:
    return Settings(
        device_id="wall",
        profile_id="crowpanel_579",
        channel_id="home",
        mode="random",
        font=FONT,
        fonts=(FontChoice("font", FONT),),
        latin_font=FONT,
        latin_fonts=(FontChoice("font", FONT),),
        library_dir=Path("/tmp"),
        refresh_minutes=30,
        active_start=datetime.strptime("07:00", "%H:%M").time(),
        active_end=datetime.strptime("22:00", "%H:%M").time(),
        items=(Item(1, "personal", "Walk"),),
        schedule=(ScheduleEntry(datetime.strptime("12:00", "%H:%M").time(), 1),),
        random_items=(1,),
        panel=PanelConfig("landscape_1", (SlotAssignment(1, "items"),)),
        status_bar=status_bar,
    )


MODULES = {
    "date": DateModule(),
    "solar_term": SolarTermModule(),
    "time": TimeModule(),
    "weekday": WeekdayModule(),
}


class SolarTermTests(unittest.TestCase):
    def test_returns_latest_started_term(self) -> None:
        self.assertEqual(current_solar_term(date(2026, 7, 16)), "小暑")
        self.assertEqual(current_solar_term(date(2026, 7, 23)), "大暑")
        self.assertEqual(current_solar_term(date(2026, 1, 1)), "冬至")
        self.assertEqual(current_solar_term(date(2026, 6, 5)), "芒种")


@unittest.skipUnless(FONT.exists(), "Source Han Sans font is not installed")
class StatusBarTests(unittest.TestCase):
    def test_centers_solar_term_and_places_weekday_on_right(self) -> None:
        configured = StatusBarConfig(
            center=(StatusAssignment("solar_term"),),
            right=(StatusAssignment("weekday"),),
        )
        image = render_status_bar(
            settings(configured), datetime(2026, 7, 16, 12, 30), MODULES,
            width=792, height=44,
        )

        self.assertEqual(image.size, (792, 44))
        self.assertEqual(image.crop((0, 0, 300, 44)).getextrema(), (255, 255))
        self.assertEqual(image.crop((300, 0, 492, 44)).getextrema(), (0, 255))
        self.assertEqual(image.crop((650, 0, 792, 44)).getextrema(), (0, 255))

    def test_weekday_module_uses_chinese_weekday(self) -> None:
        rendered = WeekdayModule().render(
            settings(StatusBarConfig()),
            datetime(2026, 7, 16, 12, 30),
            StatusAssignment("weekday"),
        )
        same_weekday = WeekdayModule().render(
            settings(StatusBarConfig()),
            datetime(2026, 7, 16, 0, 0),
            StatusAssignment("weekday"),
        )
        next_weekday = WeekdayModule().render(
            settings(StatusBarConfig()),
            datetime(2026, 7, 17, 0, 0),
            StatusAssignment("weekday"),
        )
        self.assertEqual(rendered.tobytes(), same_weekday.tobytes())
        self.assertNotEqual(rendered.tobytes(), next_weekday.tobytes())

    def test_date_module_can_remain_unconfigured(self) -> None:
        configured = StatusBarConfig(right=(StatusAssignment("time"),))
        image = render_status_bar(
            settings(configured), datetime(2026, 7, 16, 12, 30), MODULES,
            width=792, height=44,
        )
        self.assertEqual(image.crop((300, 0, 492, 44)).getextrema(), (255, 255))


if __name__ == "__main__":
    unittest.main()
