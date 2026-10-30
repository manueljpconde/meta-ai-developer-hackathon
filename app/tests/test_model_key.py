"""Missing or failing model key on the move scenario page.

Posting a move sentence with no ``META_API_KEY``, or with a key the
model endpoint refuses, must name the key clearly on the page and
must change nothing stored. No test calls the network: the
missing-key path raises before any request, and the refused-key
path stubs ``urlopen``.
"""

import os
from unittest import mock
from urllib import error as url_error

from app import store
from app.tests.helpers import AppTestCase, csrf_token
from app.tests.test_nl_move_sentence import seed_benfica

SENTENCE = "Move the Benfica payment to January"


def post_sentence_live(client, sentence):
    """Post one sentence using the real interpretation client."""
    body = client.get("/scenarios/move").body
    return client.post("/scenarios/move", {
        "sentence": sentence,
        "csrf_token": csrf_token(body),
    })


class MissingKeyPageTest(AppTestCase):
    def test_missing_key_names_key_and_saves_nothing(self):
        seed_benfica(self)
        before = self.deal_count()
        with mock.patch.dict(os.environ):
            os.environ.pop("META_API_KEY", None)
            response = post_sentence_live(self.client, SENTENCE)
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertIn("META_API_KEY", response.body)
        self.assertEqual(self.deal_count(), before)
        stored = store.list_deals(self.db_path)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["month"], "2026-11")


class RefusedKeyPageTest(AppTestCase):
    def test_refused_key_names_key_and_saves_nothing(self):
        seed_benfica(self)
        before = self.deal_count()
        refused = url_error.HTTPError(
            "https://api.meta.ai/v1/chat/completions", 401,
            "Unauthorized", {}, None)
        with mock.patch.dict(os.environ, {"META_API_KEY": "test-key"}):
            with mock.patch("urllib.request.urlopen",
                            side_effect=refused):
                response = post_sentence_live(self.client, SENTENCE)
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertIn("META_API_KEY", response.body)
        self.assertNotIn("janeiro de 2027", response.body)
        self.assertEqual(self.deal_count(), before)
        stored = store.list_deals(self.db_path)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["month"], "2026-11")


if __name__ == "__main__":
    import unittest

    unittest.main()
