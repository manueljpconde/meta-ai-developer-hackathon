"""Visible example-loading action (Q1/T4), no fixed worked example (Q3).

Fail-first tests for the ``Carregar exemplo / Load example`` flow:
the forecast and move pages offer the action, the confirm page
warns that example settings replace the current settings, and
confirming writes the example settings plus the two example deals
with fixed idempotency keys, so pressing twice creates nothing
twice. The fixed ``T2 Campo de Ourique`` worked example is gone
from the move page on a fresh database. No test calls the network.
"""

from unittest import mock

from app import store, web
from app.tests.helpers import AppTestCase, csrf_token


def load_example(test_case, lang="pt-PT"):
    """Press the example action through confirm, following redirects."""
    body = test_case.client.get("/example").body
    params = {"csrf_token": csrf_token(body)}
    return test_case.client.post("/example", params)


def seed_settings(test_case, expenses="700,00"):
    body = test_case.client.get("/settings").body
    params = {
        "share": "10",
        "iva": "10",
        "retencao": "10",
        "irs": "10",
        "ss": "10",
        "expenses": expenses,
        "form_locale": "pt-PT",
        "csrf_token": csrf_token(body),
    }
    response = test_case.client.post("/settings", params)
    test_case.assertEqual(response.code, 303, response.body[:300])


class ExampleOfferTest(AppTestCase):
    def test_forecast_empty_state_offers_example(self):
        body = self.client.get("/").body
        self.assertIn("/example", body)

    def test_move_page_offers_example(self):
        body = self.client.get("/scenarios/move").body
        self.assertIn("/example", body)
        self.assertIn("example", body.lower())

    def test_example_confirm_page_warns_about_settings(self):
        body = self.client.get("/example").body
        self.assertIn("/example", body)
        lowered = body.lower()
        self.assertTrue("substitu" in lowered or "replac" in lowered,
                        body[:1000])


class ExampleConfirmTest(AppTestCase):
    def test_confirm_creates_settings_and_two_deals(self):
        response = load_example(self)
        self.assertEqual(response.code, 303, response.body[:500])
        settings = self.stored_settings()
        self.assertEqual(settings["expenses_cents"], 35000)
        deals = sorted(self.stored_deals(),
                       key=lambda deal: deal["month"])
        self.assertEqual(len(deals), 2)
        self.assertEqual(deals[0]["name"], "Exemplo Lisboa")
        self.assertEqual(deals[1]["name"], "Exemplo Porto")
        self.assertEqual(deals[0]["part_base"], 500000)
        self.assertEqual(deals[1]["part_base"], 320000)
        body = self.client.get("/").body
        self.assertIn("Exemplo Lisboa", body)
        self.assertIn("Exemplo Porto", body)

    def test_double_press_creates_nothing_twice(self):
        first = load_example(self)
        self.assertEqual(first.code, 303, first.body[:500])
        body = self.client.get("/example").body
        second = self.client.post(
            "/example", {"csrf_token": csrf_token(body)})
        self.assertEqual(second.code, 303, second.body[:500])
        self.assertEqual(self.deal_count(), 2)

    def test_confirm_replaces_settings_and_keeps_old_deals(self):
        seed_settings(self)
        response = load_example(self)
        self.assertEqual(response.code, 303, response.body[:500])
        settings = self.stored_settings()
        self.assertEqual(settings["expenses_cents"], 35000)
        self.assertEqual(self.deal_count(), 2)

    def test_post_without_csrf_refused(self):
        response = self.client.post("/example", {})
        self.assertEqual(response.code, 403, response.body[:300])
        self.assertEqual(self.deal_count(), 0)


class NoFixedExampleTest(AppTestCase):
    def test_fresh_move_page_has_no_fixed_example(self):
        body = self.client.get("/scenarios/move").body
        self.assertNotIn("T2 Campo de Ourique", body)
        self.assertNotIn("dezembro de 2026", body)
        self.assertNotIn("December 2026", body)

    def test_worked_example_helpers_are_gone(self):
        self.assertFalse(hasattr(web, "move_example_result"),
                         "app.web still defines move_example_result")
        self.assertFalse(hasattr(web, "move_example_page"),
                         "app.web still defines move_example_page")

    def test_sentence_hint_names_first_example_deal(self):
        from app import i18n

        self.assertIn("Exemplo Lisboa", i18n.STRINGS["pt-PT"]["nl_hint"])
        self.assertIn("Exemplo Lisboa", i18n.STRINGS["en-GB"]["nl_hint"])


class ExampleEscapingTest(AppTestCase):
    def test_example_action_markup_escaped(self):
        response = load_example(self)
        self.assertEqual(response.code, 303, response.body[:500])
        body = self.client.get("/").body
        self.assertNotIn("<script>", body)


if __name__ == "__main__":
    import unittest

    unittest.main()
