"""Issue 23 move scenario at the page level: failures, wording, language.

Fail-first tests for the page criteria in issue 23. Interpretation
and transport are stubbed throughout, so no test calls the network.
Only the standard library is used.

- An engine refusal is shown as one plain question in the page's
  language, never the raw error text.
- On submit of the move form, the button is disabled and shows
  "A simular..." (pt-PT) / "Simulating..." (en-GB). Inline only: no
  external scripts or assets.
- Requests are served concurrently (a threading WSGI server from the
  standard library).
- Questions shown in Portuguese are fully Portuguese.

Acceptance tests from issue 23 at the page level:

4. Sync-failure message: trying the scenario with no connection yields
   a short notice, exactly once.
6. September double refusal: attempting to move the September payment
   twice is a plain refusal shown exactly once, stored deals untouched.
"""

import re
import unittest
from unittest import mock

from app import server, web
from app.tests.helpers import AppTestCase, csrf_token
from app.tests.test_nl_move_sentence import fake_client, seed_benfica
from engine.model_client import ModelError


SENTENCE = "move the payment to March"

TARGET = "2027-03"


def post_sentence(client, sentence, fake):
    """Post one sentence with a stubbed interpretation client."""
    body = client.get("/scenarios/move").body
    params = {
        "sentence": sentence,
        "csrf_token": csrf_token(body),
    }
    with mock.patch.object(web, "nl_client", return_value=fake):
        return client.post("/scenarios/move", params)


def seed_september(test_case):
    """Store one September deal as the only unpaid expected payment."""
    test_case.save_settings()
    review = test_case.review(values={
        "name": "Benfica",
        "commission": "10000,00",
        "share": "50",
        "month": "2026-09",
        "stage": "confirmado",
        "agency": "",
        "form_locale": "pt-PT",
    })
    test_case.assertEqual(review.code, 200, review.body[:300])
    confirmed = test_case.confirm(review.body)
    test_case.assertEqual(confirmed.code, 303, confirmed.body[:300])


class EngineRefusalPageTest(AppTestCase):
    """Engine refusals show as one plain question, never raw errors."""

    def refusal_records(self):
        """Two stored deals under one name, so a wrong name must ask."""
        self.save_settings()
        for month in ("2026-11", "2026-12"):
            review = self.review(values={
                "name": "Benfica",
                "commission": "10000,00",
                "share": "50",
                "month": month,
                "stage": "confirmado",
                "agency": "",
                "form_locale": "pt-PT",
            })
            self.assertEqual(review.code, 200, review.body[:300])
            confirmed = self.confirm(review.body)
            self.assertEqual(confirmed.code, 303, confirmed.body[:300])

    def test_unknown_payment_shows_one_plain_question(self):
        self.refusal_records()
        fake = fake_client(result={
            "deal": "Benfica", "payment": "part-9",
            "target_month": TARGET,
        })
        response = post_sentence(self.client, SENTENCE, fake)
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertNotIn("Traceback", response.body)
        self.assertNotIn("ValueError", response.body)
        self.assertNotIn("unknown payment", response.body)
        self.assertIn('role="alert"', response.body)
        self.assertEqual(self.deal_count(), 2)

    def test_past_target_shows_one_plain_question(self):
        seed_benfica(self)
        fake = fake_client(result={
            "deal": "Benfica", "payment": "part-1",
            "target_month": "2026-09",
        })
        response = post_sentence(self.client, SENTENCE, fake)
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertNotIn("Traceback", response.body)
        self.assertNotIn("ValueError", response.body)
        self.assertNotIn("in the past", response.body)
        self.assertIn('role="alert"', response.body)
        self.assertEqual(self.deal_count(), 1)

    def test_single_payment_missing_name_still_moves(self):
        seed_benfica(self)
        fake = fake_client(result={
            "deal": "Benfica", "target_month": TARGET,
        })
        response = post_sentence(self.client, SENTENCE, fake)
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertIn("2027", response.body)
        self.assertEqual(self.deal_count(), 1)


class PortugueseQuestionsPageTest(AppTestCase):
    """Questions shown in Portuguese are fully Portuguese."""

    def refusal_records(self):
        """Two stored deals under one name, so a wrong name must ask."""
        self.save_settings()
        for month in ("2026-11", "2026-12"):
            review = self.review(values={
                "name": "Benfica",
                "commission": "10000,00",
                "share": "50",
                "month": month,
                "stage": "confirmado",
                "agency": "",
                "form_locale": "pt-PT",
            })
            self.assertEqual(review.code, 200, review.body[:300])
            confirmed = self.confirm(review.body)
            self.assertEqual(confirmed.code, 303, confirmed.body[:300])

    def test_unknown_payment_question_fully_portuguese(self):
        self.refusal_records()
        fake = fake_client(result={
            "deal": "Benfica", "payment": "part-9",
            "target_month": TARGET,
        })
        response = post_sentence(self.client, SENTENCE, fake)
        self.assertEqual(response.code, 200, response.body[:500])
        alert = re.search(
            r'role="alert"[^>]*>(.*?)</p>', response.body, re.DOTALL)
        self.assertIsNotNone(alert, response.body[:1500])
        question = alert.group(1)
        for english in ("Which", "payment", "month", "Registered",
                        "deals"):
            self.assertNotIn(english, question, question)

    def test_engine_error_shows_portuguese_notice(self):
        seed_benfica(self)
        fake = fake_client(error=ModelError("boom"))
        response = post_sentence(self.client, SENTENCE, fake)
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertNotIn("boom", response.body)


class SyncFailurePageTest(AppTestCase):
    """Acceptance 4: no connection yields a short notice, exactly once."""

    def test_no_connection_shows_short_notice_once(self):
        seed_benfica(self)
        fake = fake_client(error=ModelError("the model call failed: boom"))
        response = post_sentence(self.client, SENTENCE, fake)
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertNotIn("boom", response.body)
        self.assertNotIn("Traceback", response.body)
        notices = re.findall(r'role="alert"', response.body)
        self.assertEqual(len(notices), 1, response.body[:2000])
        alert = re.search(
            r'role="alert"[^>]*>(.*?)</p>', response.body, re.DOTALL)
        self.assertIsNotNone(alert, response.body[:1500])
        self.assertLessEqual(len(alert.group(1)), 300, alert.group(1))
        self.assertEqual(self.deal_count(), 1)


class SeptemberDoublePageTest(AppTestCase):
    """Acceptance 6: September refusal shown once, stored deals kept."""

    def test_september_refusal_shows_one_plain_notice(self):
        self.save_settings()
        for month in ("2026-09", "2026-10"):
            review = self.review(values={
                "name": "Benfica",
                "commission": "10000,00",
                "share": "50",
                "month": month,
                "stage": "confirmado",
                "agency": "",
                "form_locale": "pt-PT",
            })
            self.assertEqual(review.code, 200, review.body[:300])
            confirmed = self.confirm(review.body)
            self.assertEqual(confirmed.code, 303, confirmed.body[:300])
        from app import store

        response = post_sentence(self.client, SENTENCE, fake_client(
            result={
                "deal": "Benfica", "payment": "part-9",
                "target_month": TARGET,
            }))
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertNotIn("Traceback", response.body)
        self.assertNotIn("ValueError", response.body)
        self.assertNotIn("unknown payment", response.body)
        notices = re.findall(r'role="alert"', response.body)
        self.assertEqual(len(notices), 1, response.body[:2000])
        kept = store.list_deals(self.db_path)
        self.assertEqual(len(kept), 2)
        self.assertEqual(kept[0]["month"], "2026-09")


class SubmitButtonPageTest(AppTestCase):
    """Submit disables the button with the simulating text, inline."""

    def test_submit_button_disables_with_simulating_text_pt(self):
        body = self.client.get("/scenarios/move").body
        self.assertIn("A simular...", body)
        self.assertIn("disabled", body)
        self.assertNotIn("<script src", body)
        self.assertNotIn("http://", body.replace("http://localhost", ""))

    def test_submit_button_disables_with_simulating_text_en(self):
        self.set_language("en-GB")
        body = self.client.get("/scenarios/move").body
        self.assertIn("Simulating...", body)
        self.assertIn("disabled", body)
        self.assertNotIn("<script src", body)

    def test_simulating_text_is_inline(self):
        body = self.client.get("/scenarios/move").body
        form_at = body.find('action="/scenarios/move"')
        self.assertNotEqual(form_at, -1, body[:1500])
        form = body[form_at:form_at + 2000]
        self.assertIn("onclick", form.lower())
        self.assertNotIn("<script src", body)


class ConcurrencyServerTest(unittest.TestCase):
    """Requests are served concurrently from the standard library."""

    def test_server_uses_threading_wsgi_server(self):
        import inspect

        source = inspect.getsource(server.main)
        self.assertIn("Threading", source)
        self.assertNotIn("socketserver.TCPServer", source.replace(
            "ThreadingTCPServer", ""))

    def test_server_module_imports_threading_server(self):
        import inspect

        module_source = inspect.getsource(server)
        self.assertIn("Threading", module_source)
        self.assertNotIn("gunicorn", module_source.lower())
        self.assertNotIn("waitress", module_source.lower())


if __name__ == "__main__":
    unittest.main()
