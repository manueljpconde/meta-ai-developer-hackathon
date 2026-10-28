"""Flow A review and confirmation, with the example figures.

The fixtures come from section 3 of the plan: share 50 %, IVA 23 %,
retencao 25 %, IRS 30 %, Seguranca Social 10 %, expenses 350,00 EUR,
and the negocio "T2 Campo de Ourique" with a commission of
10 000,00 EUR in November 2026, stage Confirmado.
"""

from app.tests.helpers import AppTestCase, DEAL_EN, DEAL_PT, csrf_token


class ReviewFiguresTest(AppTestCase):
    def test_review_shows_example_figures(self):
        self.save_settings()
        response = self.review()
        self.assertEqual(response.code, 200, response.body[:500])
        for expected in (
            "5 000,00",
            "4 900,00",
            "1 900,00",
            "1 150,00",
            "250,00",
            "500,00",
            "2 650,00",
        ):
            self.assertIn(expected, response.body)

    def test_review_does_not_save(self):
        self.save_settings()
        before = self.deal_count()
        response = self.review()
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertEqual(self.deal_count(), before)

    def test_review_names_month_and_labels(self):
        self.save_settings()
        response = self.review()
        self.assertEqual(response.code, 200, response.body[:500])
        for expected in (
            "novembro de 2026",
            "Comiss",
            "Entrar",
            "Dinheiro a proteger",
            "realmente teu",
        ):
            self.assertIn(expected, response.body)


class ConfirmFlowTest(AppTestCase):
    def confirm_example(self):
        self.save_settings()
        review = self.review()
        self.assertEqual(review.code, 200, review.body[:500])
        return self.confirm(review.body)

    def test_confirm_saves_example(self):
        response = self.confirm_example()
        self.assertEqual(response.code, 303, response.body[:500])
        self.assertEqual(self.deal_count(), 1)

    def test_forecast_lists_example(self):
        self.confirm_example()
        body = self.client.get("/").body
        for expected in (
            "T2 Campo de Ourique",
            "5 000,00",
            "4 900,00",
            "1 900,00",
            "2 650,00",
            "novembro de 2026",
        ):
            self.assertIn(expected, body)

    def test_confirm_twice_with_same_key_saves_once(self):
        self.save_settings()
        review = self.review()
        self.assertEqual(review.code, 200, review.body[:500])
        first = self.confirm(review.body)
        self.assertEqual(first.code, 303, first.body[:500])
        second = self.confirm(review.body)
        self.assertIn(second.code, (303, 409), second.body[:500])
        self.assertEqual(self.deal_count(), 1)

    def test_settings_changed_between_review_and_confirm(self):
        self.save_settings()
        review = self.review()
        self.assertEqual(review.code, 200, review.body[:500])
        changed = self.client.get("/settings").body
        params = {
            "share": "50",
            "iva": "23",
            "retencao": "25",
            "irs": "30",
            "ss": "10",
            "expenses": "700,00",
            "form_locale": "pt-PT",
            "csrf_token": csrf_token(changed),
        }
        saved = self.client.post("/settings", params)
        self.assertEqual(saved.code, 303, saved.body[:500])
        response = self.confirm(review.body)
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertIn("Os valores foram atualizados", response.body)
        self.assertEqual(self.deal_count(), 0)


class EnglishFiguresTest(AppTestCase):
    def test_review_in_english(self):
        self.set_language("en-GB")
        body = self.client.get("/settings").body
        params = {
            "share": "50",
            "iva": "23",
            "retencao": "25",
            "irs": "30",
            "ss": "10",
            "expenses": "350.00",
            "form_locale": "en-GB",
            "csrf_token": csrf_token(body),
        }
        saved = self.client.post("/settings", params)
        self.assertEqual(saved.code, 303, saved.body[:500])
        response = self.review(lang="en-GB")
        self.assertEqual(response.code, 200, response.body[:500])
        for expected in (
            "5,000.00",
            "4,900.00",
            "1,900.00",
            "1,150.00",
            "250.00",
            "500.00",
            "2,650.00",
            "November 2026",
        ):
            self.assertIn(expected, response.body)


class ValidationTest(AppTestCase):
    def test_missing_commission_refused(self):
        self.save_settings()
        params = dict(DEAL_PT)
        params["commission"] = ""
        response = self.review(values=params)
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertIn("Indica a comiss", response.body)
        self.assertEqual(self.deal_count(), 0)

    def test_percentage_150_refused(self):
        self.save_settings()
        params = dict(DEAL_PT)
        params["share"] = "150"
        response = self.review(values=params)
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertEqual(self.deal_count(), 0)

    def test_forecast_empty_state(self):
        body = self.client.get("/").body
        self.assertIn("Novo neg", body)
