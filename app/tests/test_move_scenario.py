"""No fixed worked example on the move page (Q3).

Example data comes only from the example-loading action: on a
fresh database the move page shows the sentence form and the
example action, and never the fixed ``T2 Campo de Ourique`` worked
example or its fixed months. Loading the page changes nothing
stored. No test calls the network.
"""

from app.tests.helpers import AppTestCase


class NoFixedExampleTest(AppTestCase):
    def test_fresh_move_page_has_no_fixed_example(self):
        body = self.client.get("/scenarios/move").body
        self.assertNotIn("T2 Campo de Ourique", body)
        self.assertNotIn("dezembro de 2026", body)
        self.assertNotIn("December 2026", body)

    def test_fresh_move_page_shows_form_and_example_action(self):
        body = self.client.get("/scenarios/move").body
        self.assertIn('name="sentence"', body)
        self.assertNotIn("/example", body)

    def test_move_page_saves_nothing(self):
        before = self.deal_count()
        response = self.client.get("/scenarios/move")
        self.assertEqual(response.code, 200, response.body[:300])
        self.assertEqual(self.deal_count(), before)

    def test_move_page_in_english_has_no_fixed_example(self):
        self.set_language("en-GB")
        body = self.client.get("/scenarios/move").body
        self.assertNotIn("T2 Campo de Ourique", body)
        self.assertNotIn("December 2026", body)
        self.assertNotIn("/example", body)


if __name__ == "__main__":
    import unittest

    unittest.main()
