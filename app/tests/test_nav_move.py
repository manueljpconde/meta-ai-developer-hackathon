"""The move scenario in the application navigation.

Fail-first tests: every page that renders the navigation contains a
link to ``/scenarios/move`` after "New deal" and before "Settings",
with the correct label in each language, and the link is marked
current on ``/scenarios/move``. No test calls the network.
"""

from app import i18n
from app.tests.helpers import AppTestCase, csrf_token

NAV_PAGES = ("/", "/deals/new", "/settings", "/example", "/scenarios/move")

LABELS = {"pt-PT": "Mover pagamento", "en-GB": "Move payment"}


class NavMoveLinkTest(AppTestCase):
    def test_i18n_labels_in_both_languages(self):
        self.assertEqual(i18n.text("pt-PT", "nav_move"), "Mover pagamento")
        self.assertEqual(i18n.text("en-GB", "nav_move"), "Move payment")

    def test_every_nav_page_links_to_move_in_portuguese(self):
        for path in NAV_PAGES:
            with self.subTest(path=path):
                body = self.client.get(path).body
                self.assertIn(
                    '<a href="/scenarios/move" data-i18n="nav_move"',
                    body,
                )
                self.assertIn("Mover pagamento", body)

    def test_every_nav_page_links_to_move_in_english(self):
        self.set_language("en-GB")
        for path in NAV_PAGES:
            with self.subTest(path=path):
                body = self.client.get(path).body
                self.assertIn(
                    '<a href="/scenarios/move" data-i18n="nav_move"',
                    body,
                )
                self.assertIn("Move payment", body)

    def test_move_link_sits_between_new_and_settings(self):
        self.set_language("en-GB")
        for path in NAV_PAGES:
            with self.subTest(path=path):
                body = self.client.get(path).body
                new = body.index('data-i18n="nav_new"')
                move = body.index('data-i18n="nav_move"')
                settings = body.index('data-i18n="nav_settings"')
                self.assertLess(new, move)
                self.assertLess(move, settings)

    def test_review_and_refused_pages_link_to_move(self):
        self.save_settings()
        review = self.review()
        self.assertEqual(review.code, 200, review.body[:300])
        self.assertIn(
            '<a href="/scenarios/move" data-i18n="nav_move"', review.body
        )
        refused = self.client.post("/deals/review", {"name": "x"})
        self.assertEqual(refused.code, 403, refused.body[:300])
        self.assertIn(
            '<a href="/scenarios/move" data-i18n="nav_move"', refused.body
        )


class NavMoveCurrentTest(AppTestCase):
    def test_move_link_marked_current_on_move_page(self):
        body = self.client.get("/scenarios/move").body
        self.assertIn(
            '<a href="/scenarios/move" data-i18n="nav_move"'
            ' aria-current="page">',
            body,
        )

    def test_move_link_not_marked_current_elsewhere(self):
        for path in ("/", "/deals/new", "/settings", "/example"):
            with self.subTest(path=path):
                body = self.client.get(path).body
                self.assertNotIn(
                    '<a href="/scenarios/move" data-i18n="nav_move"'
                    ' aria-current="page">',
                    body,
                )

    def test_other_links_marked_current_on_their_pages(self):
        cases = (
            ("/", "nav_home"),
            ("/deals/new", "nav_new"),
            ("/settings", "nav_settings"),
        )
        for path, key in cases:
            with self.subTest(path=path):
                body = self.client.get(path).body
                self.assertIn('data-i18n="%s" aria-current="page"' % key, body)


if __name__ == "__main__":
    import unittest

    unittest.main()
