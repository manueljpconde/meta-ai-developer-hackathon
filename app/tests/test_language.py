"""Language behaviour: selection, persistence and key parity.

An explicit selection always wins after that and is kept in a cookie.
The first visit takes the language from `Accept-Language` by family
(any `en-*` gives `en-GB`, any `pt-*` gives `pt-PT`, anything else
gives `pt-PT`). A language change never changes a stored value or a
result, and every string key used by the screens is present in both
languages.
"""

import re

from app import i18n
from app.tests.helpers import AppTestCase, csrf_token


class SelectionTest(AppTestCase):
    def test_first_visit_english_family(self):
        body = self.client.get("/", accept_language="en-US").body
        self.assertIn("Forecast", body)

    def test_first_visit_portuguese_family(self):
        body = self.client.get("/", accept_language="pt-BR").body
        self.assertIn("Previs", body)

    def test_first_visit_other_gives_portuguese(self):
        body = self.client.get("/", accept_language="de-DE").body
        self.assertIn("Previs", body)

    def test_explicit_switch_wins_over_later_header(self):
        self.set_language("pt-PT")
        body = self.client.get("/", accept_language="en-US").body
        self.assertIn("Previs", body)
        self.assertNotIn("Forecast", body)

    def test_switch_visible_on_every_screen(self):
        self.set_language("en-GB")
        for path in ("/", "/settings", "/deals/new"):
            body = self.client.get(path).body
            self.assertIn('name="lang"', body, path)

    def test_switch_keeps_display_only(self):
        self.save_settings()
        review = self.review()
        self.assertEqual(review.code, 200, review.body[:300])
        confirmed = self.confirm(review.body)
        self.assertEqual(confirmed.code, 303, confirmed.body[:300])
        before_pt = self.client.get("/?month=2026-11").body
        self.set_language("en-GB")
        after_en = self.client.get("/?month=2026-11").body
        self.assertIn("T2 Campo de Ourique", after_en)
        self.assertIn("November 2026", after_en)
        self.assertNotIn("novembro de 2026", after_en)
        self.assertEqual(self.deal_count(), 1)
        from app import store

        stored = self.stored_deals()
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["stage"], "confirmado")
        self.assertEqual(stored[0]["part_base"], 500000)
        self.assertIn("T2 Campo de Ourique", before_pt)


class ParityTest(AppTestCase):
    def test_every_used_key_present_in_both(self):
        keys = set()
        for path in ("/", "/settings", "/deals/new"):
            body = self.client.get(path).body
            keys.update(re.findall(r'data-i18n="([a-z_]+)"', body))
        review = self.review()
        keys.update(re.findall(r'data-i18n="([a-z_]+)"', review.body))
        self.assertGreater(len(keys), 10, keys)
        missing = [key for key in keys if key not in i18n.STRINGS["en-GB"]]
        self.assertEqual(missing, [], str(missing))
        for key in keys:
            self.assertIn(key, i18n.STRINGS["pt-PT"], key)
            self.assertTrue(i18n.STRINGS["pt-PT"][key], key)
            self.assertTrue(i18n.STRINGS["en-GB"][key], key)
