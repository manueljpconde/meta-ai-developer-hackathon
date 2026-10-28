"""Numeric input rules per locale (foundation 14.3).

`pt-PT` accepts `10000,00`, `10000` and ` 10000,00 ` as 1000000 cents
and refuses `10 000,00`, `10.000,00`, `10000.00`, `10000,005` and
`10000 EUR` with the `pt-PT` example message, keeping the typed text.
`en-GB` accepts `10000.00` and refuses `10000,00` and `10,000.00`
with the `en-GB` example message.
"""

from app.tests.helpers import AppTestCase, DEAL_EN, DEAL_PT


class PtNumericInputTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.save_settings()

    def review_commission(self, commission):
        params = dict(DEAL_PT)
        params["commission"] = commission
        return self.review(values=params)

    def test_valid_forms_accepted(self):
        for text in ("10000,00", "10000", " 10000,00 "):
            response = self.review_commission(text)
            self.assertEqual(response.code, 200, text + ": " + response.body[:300])
            self.assertIn("5 000,00", response.body, text)

    def test_invalid_forms_refused_with_example(self):
        for text in ("10 000,00", "10.000,00", "10000.00", "10000,005", "10000 EUR"):
            response = self.review_commission(text)
            self.assertEqual(response.code, 200, text + ": " + response.body[:300])
            self.assertIn("5000,50", response.body, text)
            self.assertIn(text.strip(), response.body, text)
            self.assertEqual(self.deal_count(), 0)


class EnNumericInputTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.set_language("en-GB")
        self.save_settings(
            {
                "share": "50",
                "iva": "23",
                "retencao": "25",
                "irs": "30",
                "ss": "10",
                "expenses": "350.00",
                "form_locale": "en-GB",
            }
        )

    def review_commission(self, commission):
        params = dict(DEAL_EN)
        params["commission"] = commission
        return self.review(values=params, lang="en-GB")

    def test_dot_decimal_accepted(self):
        response = self.review_commission("10000.00")
        self.assertEqual(response.code, 200, response.body[:300])
        self.assertIn("5,000.00", response.body)

    def test_comma_forms_refused_with_example(self):
        for text in ("10000,00", "10,000.00"):
            response = self.review_commission(text)
            self.assertEqual(response.code, 200, text + ": " + response.body[:300])
            self.assertIn("5000.50", response.body, text)
            self.assertEqual(self.deal_count(), 0)
