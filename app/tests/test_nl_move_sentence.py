"""Natural-language move sentence on the scenario page.

Fail-first tests for typing one move sentence on /scenarios/move:
a clear move shows the before and after forecast, an ambiguous
sentence or an unknown deal shows one focused question instead of
guessing, a model failure shows an error and moves nothing, and
nothing stored ever changes. Interpretation runs through a fake
client, so no test calls the network.
"""

from unittest import mock

from app import web
from app.tests.helpers import AppTestCase, csrf_token


SENTENCE = "Move the Benfica payment to January"


def fake_client(result=None, error=None):
    """A fake interpretation client with the live client interface."""

    class Fake:
        def interpret_move(self, sentence):
            Fake.seen.append(sentence)
            if error is not None:
                raise error
            if isinstance(result, dict):
                return dict(result)
            return result

    Fake.seen = []
    return Fake()


def post_sentence(client, sentence, fake):
    body = client.get("/scenarios/move").body
    params = {
        "sentence": sentence,
        "csrf_token": csrf_token(body),
    }
    with mock.patch.object(web, "nl_client", return_value=fake):
        return client.post("/scenarios/move", params)


def seed_benfica(test_case):
    """Store one Benfica deal as the only unpaid expected payment."""
    test_case.save_settings()
    review = test_case.review(values={
        "name": "Benfica",
        "commission": "10000,00",
        "share": "50",
        "month": "2026-11",
        "stage": "confirmado",
        "agency": "",
        "form_locale": "pt-PT",
    })
    test_case.assertEqual(review.code, 200, review.body[:300])
    confirmed = test_case.confirm(review.body)
    test_case.assertEqual(confirmed.code, 303, confirmed.body[:300])


class ClearMovePageTest(AppTestCase):
    def test_clear_sentence_shows_before_and_after(self):
        seed_benfica(self)
        fake = fake_client(result={
            "deal": "Benfica", "payment": "part-1",
            "target_month": "2027-01",
        })
        response = post_sentence(self.client, SENTENCE, fake)
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertEqual(fake.seen, [SENTENCE])
        for expected in (
            "Benfica",
            "novembro de 2026",
            "janeiro de 2027",
            "5 000,00",
        ):
            self.assertIn(expected, response.body)

    def test_clear_sentence_saves_nothing(self):
        seed_benfica(self)
        before = self.deal_count()
        fake = fake_client(result={
            "deal": "Benfica", "payment": "part-1",
            "target_month": "2027-01",
        })
        response = post_sentence(self.client, SENTENCE, fake)
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertEqual(self.deal_count(), before)
        from app import store

        stored = self.stored_deals()
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["month"], "2026-11")

    def test_move_page_shows_sentence_form(self):
        body = self.client.get("/scenarios/move").body
        self.assertIn('name="sentence"', body)
        self.assertIn("csrf_token", body)


class QuestionPageTest(AppTestCase):
    def test_ambiguous_sentence_asks_one_question(self):
        seed_benfica(self)
        fake = fake_client(result={
            "question": "Which Benfica payment did you mean?",
        })
        response = post_sentence(self.client, "Move the payment", fake)
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertIn("Which Benfica payment did you mean?", response.body)
        self.assertEqual(self.deal_count(), 1)

    def test_unknown_deal_asks_instead_of_guessing(self):
        seed_benfica(self)
        fake = fake_client(result={
            "deal": "No Such Deal", "payment": "part-1",
            "target_month": "2027-01",
        })
        response = post_sentence(self.client, SENTENCE, fake)
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertIn("No Such Deal", response.body)
        self.assertEqual(self.deal_count(), 1)

    def test_empty_sentence_asks_without_calling_model(self):
        seed_benfica(self)
        fake = fake_client(result={
            "deal": "Benfica", "payment": "part-1",
            "target_month": "2027-01",
        })
        response = post_sentence(self.client, "   ", fake)
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertEqual(fake.seen, [])
        self.assertEqual(self.deal_count(), 1)


class ModelFailurePageTest(AppTestCase):
    def test_model_failure_is_an_error_not_a_guess(self):
        from engine.model_client import ModelError

        seed_benfica(self)
        fake = fake_client(error=ModelError("boom"))
        response = post_sentence(self.client, SENTENCE, fake)
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertNotIn("janeiro de 2027", response.body)
        self.assertEqual(self.deal_count(), 1)


class SentenceSecurityTest(AppTestCase):
    def test_post_without_csrf_refused(self):
        seed_benfica(self)
        fake = fake_client(result={
            "deal": "Benfica", "payment": "part-1",
            "target_month": "2027-01",
        })
        with mock.patch.object(web, "nl_client", return_value=fake):
            response = self.client.post(
                "/scenarios/move", {"sentence": SENTENCE})
        self.assertEqual(response.code, 403, response.body[:300])
        self.assertEqual(fake.seen, [])
        self.assertEqual(self.deal_count(), 1)

    def test_sentence_markup_escaped(self):
        seed_benfica(self)
        markup = "<script>alert(1)</script>"
        fake = fake_client(result={"question": "Which payment?"})
        response = post_sentence(self.client, markup, fake)
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertNotIn(markup, response.body)
        self.assertIn("&lt;script&gt;", response.body)


if __name__ == "__main__":
    import unittest

    unittest.main()
