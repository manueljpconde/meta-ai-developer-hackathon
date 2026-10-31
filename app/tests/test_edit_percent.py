"""Pre-filled percentages stay plain decimals in both languages.

Regression tests for the scientific-notation pre-filled values: the
stored rates shown by ``format_edit_percent`` must render as plain
decimal digits with the locale's separator, parse back to exactly the
same stored rate, and survive the settings and new-deal forms
unchanged in ``pt-PT`` and ``en-GB``.
"""

import re
import unittest
from decimal import Decimal

from app import store, web
from app.tests.helpers import AppTestCase, csrf_token, hidden_inputs

RATES = ("0.5", "0.1", "0.3", "1", "0.23", "0.125", "0")
EXPECTED_PT = ("50", "10", "30", "100", "23", "12,5", "0")
EXPECTED_EN = ("50", "10", "30", "100", "23", "12.5", "0")

SETTINGS_EN = {
    "share": "50",
    "iva": "23",
    "retencao": "25",
    "irs": "30",
    "ss": "10",
    "expenses": "350.00",
    "form_locale": "en-GB",
}


def input_value(body, name):
    """Value of the visible input called ``name`` in an HTML page."""
    match = re.search(
        r'name="%s" value="([^"]*)"' % re.escape(name), body
    )
    return match.group(1) if match is not None else ""


class FormatEditPercentTest(unittest.TestCase):
    def test_pt_values(self):
        for rate, expected in zip(RATES, EXPECTED_PT):
            self.assertEqual(
                web.format_edit_percent(rate, "pt-PT"), expected, rate
            )

    def test_en_values(self):
        for rate, expected in zip(RATES, EXPECTED_EN):
            self.assertEqual(
                web.format_edit_percent(rate, "en-GB"), expected, rate
            )

    def test_no_exponent_for_any_table_rate(self):
        for lang in ("pt-PT", "en-GB"):
            for rate in RATES:
                shown = web.format_edit_percent(rate, lang)
                self.assertNotIn("E", shown, (rate, lang))
                self.assertNotIn("e", shown, (rate, lang))

    def test_round_trip_both_languages(self):
        for lang in ("pt-PT", "en-GB"):
            for rate in RATES:
                shown = web.format_edit_percent(rate, lang)
                try:
                    back = web.parse_percent(shown, lang)
                except ValueError:
                    self.fail(
                        "cannot parse pre-filled %r for rate %s in %s"
                        % (shown, rate, lang)
                    )
                self.assertEqual(back / 100, Decimal(rate), (rate, lang))


class PrefilledDealJourneyTest(AppTestCase):
    def run_prefilled_deal(self, lang, settings, commission,
                           expected_figure, expected_label):
        if lang != "pt-PT":
            self.set_language(lang)
        self.save_settings(settings)
        form = self.client.get("/deals/new").body
        share = input_value(form, "share")
        self.assertTrue(share, "new-deal form has no pre-filled share")
        params = {
            "name": "T2 Campo de Ourique",
            "commission": commission,
            "share": share,
            "month": "2026-11",
            "stage": "confirmado",
            "form_locale": lang,
            "csrf_token": csrf_token(form),
        }
        response = self.client.post("/deals/review", params)
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertIn(expected_label, response.body)
        self.assertIn(expected_figure, response.body)
        self.assertNotIn('class="error"', response.body)
        confirmed = self.confirm(response.body)
        self.assertEqual(confirmed.code, 303, confirmed.body[:500])
        self.assertEqual(self.deal_count(), 1)

    def test_prefilled_deal_pt(self):
        from app.tests.helpers import SETTINGS_PT

        self.run_prefilled_deal(
            "pt-PT", SETTINGS_PT, "10000,00", "5 000,00", "A tua parte"
        )

    def test_prefilled_deal_en(self):
        self.run_prefilled_deal(
            "en-GB", SETTINGS_EN, "10000.00", "5,000.00", "Your share"
        )


class PrefilledSettingsRoundTripTest(AppTestCase):
    def run_settings_round_trip(self, lang, settings):
        if lang != "pt-PT":
            self.set_language(lang)
        self.save_settings(settings)
        before = self.stored_settings()
        body = self.client.get("/settings").body
        hidden = hidden_inputs(body)
        params = {
            name: input_value(body, name)
            for name in ("share", "iva", "retencao", "irs", "ss",
                         "expenses")
        }
        params["form_locale"] = hidden["form_locale"]
        params["csrf_token"] = hidden["csrf_token"]
        response = self.client.post("/settings", params)
        self.assertEqual(response.code, 303, response.body[:500])
        self.assertEqual(self.stored_settings(), before)

    def test_settings_round_trip_pt(self):
        from app.tests.helpers import SETTINGS_PT

        self.run_settings_round_trip("pt-PT", SETTINGS_PT)

    def test_settings_round_trip_en(self):
        self.run_settings_round_trip("en-GB", SETTINGS_EN)


if __name__ == "__main__":
    unittest.main()
