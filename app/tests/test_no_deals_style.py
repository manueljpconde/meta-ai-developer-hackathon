"""No-deals move page (D3/T5) and style tokens (T6).

Fail-first tests: with no registered deals the move page shows the
sentence form plus a notice with links to New deal and the example
action, and posting a sentence asks without calling the model.
The stylesheet carries the agreed light-theme tokens, the Figtree
stack with no external assets, ink primary buttons with an accent
focus ring, and a viewport meta tag on the page shell. No test
calls the network.
"""

import os
from unittest import mock

from app import web
from app.tests.helpers import AppTestCase, csrf_token
from app.tests.test_nl_move_sentence import fake_client


def post_sentence(client, sentence, fake):
    body = client.get("/scenarios/move").body
    params = {
        "sentence": sentence,
        "csrf_token": csrf_token(body),
    }
    with mock.patch.object(web, "nl_client", return_value=fake):
        return client.post("/scenarios/move", params)


class NoDealsMovePageTest(AppTestCase):
    def test_notice_with_both_links(self):
        body = self.client.get("/scenarios/move").body
        self.assertIn('name="sentence"', body)
        lowered = body.lower()
        self.assertTrue("no deal" in lowered or "sem neg" in lowered
                        or "ainda n" in lowered, body[:1500])
        self.assertIn("/deals/new", body)
        self.assertIn("/example", body)

    def test_post_with_no_deals_asks_without_calling_model(self):
        fake = fake_client(result={
            "deal": "Benfica", "payment": "part-1",
            "target_month": "2027-01",
        })
        response = post_sentence(self.client, "Move the payment", fake)
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertEqual(fake.seen, [])
        lowered = response.body.lower()
        self.assertTrue("example" in lowered or "exemplo" in lowered
                        or "deal" in lowered or "neg" in lowered,
                        response.body[:1500])
        self.assertEqual(self.deal_count(), 0)

    def test_empty_sentence_with_no_deals_asks_without_model(self):
        fake = fake_client(result={
            "deal": "Benfica", "payment": "part-1",
            "target_month": "2027-01",
        })
        response = post_sentence(self.client, "   ", fake)
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertEqual(fake.seen, [])


class StyleTokensTest(AppTestCase):
    def read_css(self):
        path = os.path.join(os.path.dirname(web.__file__),
                            "static", "style.css")
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def test_light_theme_tokens(self):
        css = self.read_css()
        for token in ("#f6f7f4", "#16302c", "#5f6f6a", "#f2b705",
                      "#fdf3d0", "#a7cec0", "#e6ebe8", "#9e2f25",
                      "#f6e2de", "#2f5b8a", "#e4ecf5"):
            self.assertIn(token, css, token)

    def test_font_stack_without_external_assets(self):
        css = self.read_css()
        self.assertIn("Figtree", css)
        self.assertIn("system-ui", css)
        self.assertNotIn("@import", css)
        self.assertNotIn("http://", css)
        self.assertNotIn("https://", css)

    def test_primary_buttons_and_focus(self):
        css = self.read_css()
        self.assertIn("button", css)
        self.assertIn("#16302c", css)
        self.assertIn("#f2b705", css)

    def test_viewport_and_responsive_layout(self):
        body = self.client.get("/").body
        self.assertIn('name="viewport"', body)
        css = self.read_css()
        self.assertIn("max-width", css)


if __name__ == "__main__":
    import unittest

    unittest.main()
