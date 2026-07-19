import unittest

from home_companian.config import ConfigError
from home_companian.domain import PanelConfig, SlotAssignment
from home_companian.templates import load_template, validate_panel


class TemplateTests(unittest.TestCase):
    def test_loads_full_screen_template(self) -> None:
        template = load_template("landscape_1")

        self.assertEqual((template.width, template.height), (792, 228))
        self.assertEqual(template.slot(1).width, 792)

    def test_rejects_unknown_template(self) -> None:
        with self.assertRaisesRegex(ConfigError, "unknown panel template"):
            load_template("missing")

    def test_loads_two_slot_template(self) -> None:
        template = load_template("landscape_2")
        self.assertEqual(template.slot(1).width, 528)
        self.assertEqual(template.slot(2).x, 528)
        self.assertEqual(template.slot(2).height, 228)

    def test_loads_three_slot_template_with_square_sides(self) -> None:
        template = load_template("landscape_3")
        self.assertEqual(
            (template.slot(1).x, template.slot(1).y, template.slot(1).width, template.slot(1).height),
            (0, 14, 200, 200),
        )
        self.assertEqual((template.slot(2).x, template.slot(2).width), (212, 368))
        self.assertEqual(
            (template.slot(3).x, template.slot(3).y, template.slot(3).width, template.slot(3).height),
            (592, 14, 200, 200),
        )

    def test_loads_kindle_portrait_template(self) -> None:
        template = load_template("portrait_1")
        self.assertEqual((template.width, template.height), (600, 760))
        self.assertEqual(
            (template.slot(1).width, template.slot(1).height),
            (600, 760),
        )

    def test_loads_kindle_landscape_template(self) -> None:
        template = load_template("landscape_4")
        self.assertEqual((template.width, template.height), (800, 560))
        self.assertEqual(
            (template.slot(1).width, template.slot(1).height),
            (800, 560),
        )

    def test_rejects_assignment_to_unknown_slot(self) -> None:
        panel = PanelConfig("landscape_1", (SlotAssignment(2, "items"),))
        with self.assertRaisesRegex(ConfigError, "has no slot 2"):
            validate_panel(panel)

    def test_allows_empty_slots(self) -> None:
        template = validate_panel(PanelConfig("landscape_1", ()))
        self.assertEqual(template.id, "landscape_1")


if __name__ == "__main__":
    unittest.main()
