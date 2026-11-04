"""Hotfix proof: hardened client rejects double start_response and valid link signs in."""

import os
import tempfile
import unittest

from app.tests.helpers import Client, open_link
from app import web


class DoubleStartResponseTest(unittest.TestCase):
    def test_client_fails_on_second_start_response(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        web.DB_PATH = tmp.name + "/test.db"
        client = Client()

        def crashing_app(environ, start_response):
            start_response("200 OK", [("Content-Type", "text/plain")])
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"hi"]

        orig = web.application
        web.application = crashing_app
        self.addCleanup(lambda: setattr(web, "application", orig))
        with self.assertRaises(AssertionError) as ctx:
            client.get("/")
        self.assertIn("Headers already set", str(ctx.exception))


class ValidLinkEndToEndTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = tmp.name + "/test.db"
        web.DB_PATH = self.db_path
        self.client = Client()
        # No pre-authentication: exercise real sign-in flow
        self.client.cookies = {}

    def test_valid_link_signs_in_through_hardened_client(self):
        from app import auth
        # Create a valid link directly (no network, no mail)
        ok, token = auth.request_link(self.db_path, "alice@example.com", "1.1.1.1", lang="pt-PT")
        self.assertTrue(ok)
        # Verify navigates to / with session cookie
        resp = open_link(self.client, token)
        self.assertEqual(resp.code, 303, resp.body[:500])
        self.assertIn("/", resp.headers.get("location", ""))
        cookies = " ".join(self.client.last_set_cookies)
        self.assertIn("session=", cookies)
        self.assertIn("HttpOnly", cookies)
        self.assertIn("SameSite=Lax", cookies)
        # Client now carries session; home renders 200
        home = self.client.get("/")
        self.assertEqual(home.code, 200)
        self.assertIn("session", self.client.cookies)

    def test_secure_flag_when_https_base(self):
        from app import auth
        ok, token = auth.request_link(self.db_path, "bob@example.com", "2.2.2.2", lang="pt-PT")
        self.assertTrue(ok)
        prev = os.environ.get("APP_BASE_URL")
        os.environ["APP_BASE_URL"] = "https://example.com"
        self.addCleanup(lambda: os.environ.pop("APP_BASE_URL", None) if prev is None else os.environ.__setitem__("APP_BASE_URL", prev))
        resp = open_link(self.client, token)
        self.assertEqual(resp.code, 303)
        cookies = " ".join(self.client.last_set_cookies)
        self.assertIn("Secure", cookies)
        # http base must not add Secure
        os.environ["APP_BASE_URL"] = "http://example.com"
        ok2, token2 = auth.request_link(self.db_path, "carol@example.com", "3.3.3.3", lang="pt-PT")
        self.assertTrue(ok2)
        resp2 = open_link(self.client, token2)
        self.assertEqual(resp2.code, 303)
        cookies2 = " ".join(self.client.last_set_cookies)
        # last cookie from this request should not contain Secure (http)
        # extract last Set-Cookie header
        last = self.client.last_set_cookies[-1] if self.client.last_set_cookies else ""
        self.assertNotIn("Secure", last)


class OpeningALinkChangesNothingTest(unittest.TestCase):
    """iPhone 2026-11-04: the mail app fetched every link first, so the agent's tap found it used."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = tmp.name + "/test.db"
        web.DB_PATH = self.db_path
        from app import auth
        ok, self.token = auth.request_link(self.db_path, "iphone@example.com", "9.9.9.9", lang="pt-PT")
        self.assertTrue(ok)

    def test_a_preview_fetch_then_the_agents_tap_signs_in(self):
        preview = Client()
        for _ in range(3):
            self.assertEqual(preview.get("/auth/verify?token=" + self.token).code, 200)
        self.assertNotIn("session=", " ".join(preview.last_set_cookies).replace("session=;", ""))
        agent = Client()
        response = open_link(agent, self.token)
        self.assertEqual(response.code, 303)
        self.assertEqual(agent.get("/").code, 200)

    def test_the_page_shows_a_sign_in_button_that_posts(self):
        body = Client().get("/auth/verify?token=" + self.token).body
        self.assertIn('<form method="post" action="/auth/verify">', body)
        self.assertIn("Entrar", body)

    def test_a_post_without_the_page_token_uses_nothing(self):
        client = Client()
        client.get("/auth/verify?token=" + self.token)
        refused = client.post("/auth/verify", {"token": self.token, "csrf_token": "wrong"})
        self.assertEqual(refused.code, 200)
        self.assertEqual(open_link(Client(), self.token).code, 303, "the link is still unused")

    def test_a_used_link_says_so_when_opened(self):
        open_link(Client(), self.token)
        again = Client().get("/auth/verify?token=" + self.token)
        self.assertIn('data-i18n="auth_invalid"', again.body)
        self.assertNotIn('action="/auth/verify"', again.body)
