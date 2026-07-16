import unittest

from home_companian.http_server import parse_battery


class HttpServerTests(unittest.TestCase):
    def test_parses_optional_battery(self) -> None:
        self.assertIsNone(parse_battery(""))
        self.assertEqual(parse_battery("battery=82"), 82)

    def test_rejects_invalid_battery(self) -> None:
        for query in ("battery=-1", "battery=101", "battery=nope"):
            with self.subTest(query=query), self.assertRaises(ValueError):
                parse_battery(query)


if __name__ == "__main__":
    unittest.main()
