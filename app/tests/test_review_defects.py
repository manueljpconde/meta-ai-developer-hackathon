"""Section 3 defects: engine share, exact storage, body and field limits.

Fail-first tests for the four review defects: the app computes one
deal's share through ``engine.calc.agent_share`` with no money
arithmetic of its own, stores form input exactly as typed, refuses
oversized and non-UTF-8 bodies, and refuses overlong text fields
beside the field, in both languages.
"""

import io
import unittest

from app import store, web
from app.tests.helpers import (
    AppTestCase,
    DEAL_EN,
    DEAL_PT,
    csrf_token,
    hidden_inputs,
)


UX_SHARE_PT = "5 000,00"
ENTITY = "&lt;b&gt;"
ESCAPED_ENTITY = "&amp;lt;b&amp;gt;"
TOO_LONG_PT = "200 caracteres"
TOO_LONG_EN = "200 characters"


class TrackingInput(io.BytesIO):
    """Bytes stream recording whether it was read."""

    def __init__(self, data):
        super().__init__(data)
        self.read_called = False

    def read(self, *args, **kwargs):
        self.read_called = True
        return super().read(*args, **kwargs)


def raw_post(path, body, content_length=None):
    """POST raw bytes, returning (status code, body text, stream)."""
    stream = TrackingInput(body)
    environ = {
        "REQUEST_METHOD": "POST",
        "SCRIPT_NAME": "",
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "CONTENT_TYPE": "application/x-www-form-urlencoded",
        "CONTENT_LENGTH": (
            str(len(body)) if content_length is None else content_length
        ),
        "wsgi.input": stream,
        "wsgi.url_scheme": "http",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "8000",
    }
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    chunks = web.application(environ, start_response)
    text = b"".join(chunks).decode("utf-8", "replace")
    code = int(captured["status"].split()[0])
    return code, text, stream


class ShareThroughEngineTest(AppTestCase):
    def test_no_money_arithmetic_in_app(self):
        self.assertFalse(
            hasattr(web, "derive_share"),
            "app.web still defines derive_share",
        )

    def test_share_comes_from_engine(self):
        self.assertTrue(
            callable(getattr(web, "agent_share", None)),
            "app.web does not use engine.calc.agent_share",
        )

    def test_example_share_figure(self):
        self.save_settings()
        response = self.review()
        self.assertEqual(response.code, 200, response.body[:300])
        self.assertIn(UX_SHARE_PT, response.body)


class ExactStorageTest(AppTestCase):
    def review_entity(self):
        self.save_settings()
        params = dict(DEAL_PT)
        params["name"] = ENTITY
        review = self.review(values=params)
        self.assertEqual(review.code, 200, review.body[:300])
        return review

    def test_entity_stored_exactly(self):
        review = self.review_entity()
        response = self.confirm(review.body)
        self.assertEqual(response.code, 303, response.body[:300])
        stored = store.list_deals(self.db_path)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["name"], ENTITY)

    def test_entity_shown_escaped_once(self):
        review = self.review_entity()
        response = self.confirm(review.body)
        self.assertEqual(response.code, 303, response.body[:300])
        body = self.client.get("/?month=2026-11").body
        self.assertIn(ESCAPED_ENTITY, body)


class BodyLimitTest(AppTestCase):
    def test_oversized_body_refused_before_read(self):
        code, text, stream = raw_post(
            "/deals/review", b"x=1", content_length="65537")
        self.assertEqual(code, 413, text[:300])
        self.assertFalse(stream.read_called, "oversized body was read")
        self.assertEqual(self.deal_count(), 0)

    def test_limit_is_exact(self):
        code, _, stream = raw_post(
            "/deals/review", b"x=1", content_length="65536")
        self.assertNotEqual(code, 413)
        self.assertTrue(stream.read_called)

    def test_non_utf8_body_refused(self):
        try:
            code, text, _ = raw_post(
                "/deals/review", b"name=\xff\xfe&csrf_token=x")
        except UnicodeDecodeError:
            code, text = None, ""
        self.assertEqual(code, 400, text[:300])
        self.assertEqual(self.deal_count(), 0)


class FieldLimitTest(AppTestCase):
    def confirm_direct(self, params, csrf_body):
        params = dict(params)
        params["csrf_token"] = csrf_token(csrf_body)
        return self.client.post("/deals/confirm", params)

    def test_long_name_refused_pt(self):
        self.save_settings()
        params = dict(DEAL_PT)
        params["name"] = "n" * 201
        review = self.review(values=params)
        self.assertEqual(review.code, 200, review.body[:300])
        self.assertIn(TOO_LONG_PT, review.body)
        fresh = self.client.get("/deals/new").body
        self.confirm_direct(params, fresh)
        self.assertEqual(self.deal_count(), 0)

    def test_long_name_refused_en(self):
        self.set_language("en-GB")
        body = self.client.get("/settings").body
        settings = {
            "share": "50",
            "iva": "23",
            "retencao": "25",
            "irs": "30",
            "ss": "10",
            "expenses": "350.00",
            "form_locale": "en-GB",
            "csrf_token": csrf_token(body),
        }
        saved = self.client.post("/settings", settings)
        self.assertEqual(saved.code, 303, saved.body[:300])
        params = dict(DEAL_EN)
        params["form_locale"] = "en-GB"
        params["name"] = "n" * 201
        review = self.review(values=params, lang="en-GB")
        self.assertEqual(review.code, 200, review.body[:300])
        self.assertIn(TOO_LONG_EN, review.body)
        self.assertEqual(self.deal_count(), 0)

    def test_long_agency_refused(self):
        self.save_settings()
        params = dict(DEAL_PT)
        params["agency"] = "a" * 201
        review = self.review(values=params)
        self.assertEqual(review.code, 200, review.body[:300])
        self.assertIn(TOO_LONG_PT, review.body)
        self.assertEqual(self.deal_count(), 0)

    def test_boundary_name_accepted(self):
        self.save_settings()
        params = dict(DEAL_PT)
        params["name"] = "n" * 200
        review = self.review(values=params)
        self.assertEqual(review.code, 200, review.body[:300])
        self.assertIn(UX_SHARE_PT, review.body)
        shown = hidden_inputs(review.body)
        params.update({
            "csrf_token": csrf_token(review.body),
            "shown_share": shown["shown_share"],
            "shown_bank": shown["shown_bank"],
            "shown_protected": shown["shown_protected"],
            "shown_really": shown["shown_really"],
            "idempotency_key": shown["idempotency_key"],
        })
        confirmed = self.client.post("/deals/confirm", params)
        self.assertEqual(confirmed.code, 303, confirmed.body[:300])
        self.assertEqual(self.deal_count(), 1)


if __name__ == "__main__":
    unittest.main()
