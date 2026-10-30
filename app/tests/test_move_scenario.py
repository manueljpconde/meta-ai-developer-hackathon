"""Move-payment scenario example in the app.

The app shows the before and after forecast for one example move:
the expected payment of 5 000,00 EUR in November 2026 moves to
December 2026. The page changes nothing stored; it only displays.
"""

from app.tests.helpers import AppTestCase


class MoveExampleTest(AppTestCase):
    def test_move_example_shows_before_and_after(self):
        body = self.client.get("/scenarios/move").body
        self.assertIn("novembro de 2026", body)
        self.assertIn("dezembro de 2026", body)

    def test_move_example_shows_example_figures(self):
        response = self.client.get("/scenarios/move")
        self.assertEqual(response.code, 200, response.body[:300])
        for expected in (
            "T2 Campo de Ourique",
            "5 000,00",
            "4 900,00",
            "1 900,00",
            "2 650,00",
        ):
            self.assertIn(expected, response.body)

    def test_move_example_before_after_sections(self):
        body = self.client.get("/scenarios/move").body
        before = body.find("novembro de 2026")
        after = body.find("dezembro de 2026")
        self.assertNotEqual(before, -1)
        self.assertNotEqual(after, -1)
        self.assertLess(before, after)

    def test_move_example_saves_nothing(self):
        before = self.deal_count()
        response = self.client.get("/scenarios/move")
        self.assertEqual(response.code, 200, response.body[:300])
        self.assertEqual(self.deal_count(), before)

    def test_move_example_in_english(self):
        self.set_language("en-GB")
        body = self.client.get("/scenarios/move").body
        self.assertIn("November 2026", body)
        self.assertIn("December 2026", body)
        self.assertIn("5,000.00", body)


if __name__ == "__main__":
    import unittest

    unittest.main()
