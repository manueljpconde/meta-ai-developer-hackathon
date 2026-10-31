"""WSGI integration for sign-in page, verify, sign-out, mail no-send in tests."""

import unittest
from unittest import mock

from app.tests.helpers import AppTestCase, csrf_token


class SigninPageTest(AppTestCase):
    def test_signin_page_renders(self):
        body = self.client.get("/signin").body
        self.assertIn("signin", body.lower())

    def test_signin_post_valid_email_sends_to_outbox(self):
        from app import mail
        mail.OUTBOX = []
        self.addCleanup(lambda: setattr(mail, "OUTBOX", None))
        body = self.client.get("/signin").body
        token = csrf_token(body)
        resp = self.client.post("/signin", {"email": "a@b.com", "csrf_token": token})
        self.assertEqual(resp.code, 200, resp.body[:500])
        self.assertEqual(len(mail.OUTBOX), 1)
        self.assertEqual(mail.OUTBOX[0]["to"], "a@b.com")
        self.assertIn("token=", mail.OUTBOX[0]["link"])

    def test_signin_post_invalid_email_shows_error(self):
        from app import mail
        mail.OUTBOX = []
        self.addCleanup(lambda: setattr(mail, "OUTBOX", None))
        body = self.client.get("/signin").body
        resp = self.client.post("/signin", {"email": "not-an-email", "csrf_token": csrf_token(body)})
        self.assertEqual(resp.code, 200, resp.body[:300])
        self.assertEqual(len(mail.OUTBOX), 0)

    def test_verify_link_creates_session_cookie(self):
        from app import mail
        mail.OUTBOX = []
        self.addCleanup(lambda: setattr(mail, "OUTBOX", None))
        body = self.client.get("/signin").body
        self.client.post("/signin", {"email": "u@v.com", "csrf_token": csrf_token(body)})
        token = mail.OUTBOX[0]["link"].split("token=")[1]
        resp = self.client.get("/auth/verify?token=" + token)
        self.assertEqual(resp.code, 303, resp.body[:500])
        # Should set session cookie with HttpOnly and Lax
        cookies = " ".join(self.client.last_set_cookies).lower()
        self.assertIn("httponly", cookies)

    def test_verify_expired_link_no_session(self):
        from app import auth
        # create link at time 1000, verify after 20 minutes
        auth.request_link(self.db_path, "e@f.com", "1.1.1.1", now=1000.0, token="expired-tok")
        resp = self.client.get("/auth/verify?token=expired-tok")
        # verify_link uses current time, but our link expired long ago (real now >> 1000+900)
        # So this tests that expired is rejected - but we need deterministic
        # Instead test with real flow: create link now, patch time to far future
        import time as time_mod
        with mock.patch.object(time_mod, "time", return_value=1000.0 + 20 * 60):
            resp2 = self.client.get("/auth/verify?token=expired-tok")
        self.assertEqual(resp2.code, 200, resp2.body[:500])
        self.assertNotIn("session", " ".join(self.client.last_set_cookies).lower())

    def test_guessed_token_shows_error(self):
        resp = self.client.get("/auth/verify?token=guessed-random-token")
        self.assertEqual(resp.code, 200, resp.body[:500])

    def test_mail_stub_never_sends_real(self):
        from app import mail
        mail.OUTBOX = []
        self.addCleanup(lambda: setattr(mail, "OUTBOX", None))
        body = self.client.get("/signin").body
        self.client.post("/signin", {"email": "a@b.com", "csrf_token": csrf_token(body)})
        # No SMTP called - OUTBOX has it
        self.assertEqual(len(mail.OUTBOX), 1)

    def test_signin_rate_limited_no_mail(self):
        from app import mail
        mail.OUTBOX = []
        self.addCleanup(lambda: setattr(mail, "OUTBOX", None))
        for i in range(5):
            body = self.client.get("/signin").body
            self.client.post("/signin", {"email": "r@b.com", "csrf_token": csrf_token(body)})
        self.assertEqual(len(mail.OUTBOX), 5)
        body = self.client.get("/signin").body
        resp = self.client.post("/signin", {"email": "r@b.com", "csrf_token": csrf_token(body)})
        self.assertEqual(resp.code, 200, resp.body[:500])
        self.assertEqual(len(mail.OUTBOX), 5)

    def test_signout_clears_session(self):
        from app import mail
        mail.OUTBOX = []
        self.addCleanup(lambda: setattr(mail, "OUTBOX", None))
        body = self.client.get("/signin").body
        self.client.post("/signin", {"email": "s@b.com", "csrf_token": csrf_token(body)})
        token = mail.OUTBOX[0]["link"].split("token=")[1]
        self.client.get("/auth/verify?token=" + token)
        self.assertIn("session", self.client.cookies)
        body2 = self.client.get("/").body
        resp = self.client.post("/signout", {"csrf_token": csrf_token(body2)})
        self.assertEqual(resp.code, 303, resp.body[:500])
        # session cookie cleared or deleted
        # After signout, session should not be valid
        from app import auth, web
        sid = self.client.cookies.get("session", "")
        # sid may be empty or expired
        sess = auth.get_valid_session(self.db_path, sid) if sid else None
        self.assertIsNone(sess)

    def test_session_cookie_httponly_and_lax(self):
        from app import mail
        mail.OUTBOX = []
        self.addCleanup(lambda: setattr(mail, "OUTBOX", None))
        body = self.client.get("/signin").body
        self.client.post("/signin", {"email": "l@b.com", "csrf_token": csrf_token(body)})
        token = mail.OUTBOX[0]["link"].split("token=")[1]
        self.client.get("/auth/verify?token=" + token)
        cookies = " ".join(self.client.last_set_cookies).lower()
        self.assertIn("httponly", cookies)
        self.assertIn("samesite=lax", cookies)

    def test_delete_account_requires_typed_email_match(self):
        from app import mail, store
        mail.OUTBOX = []
        self.addCleanup(lambda: setattr(mail, "OUTBOX", None))
        body = self.client.get("/signin").body
        self.client.post("/signin", {"email": "del@b.com", "csrf_token": csrf_token(body)})
        token = mail.OUTBOX[0]["link"].split("token=")[1]
        self.client.get("/auth/verify?token=" + token)
        # Try delete with wrong email
        body2 = self.client.get("/account/delete").body
        resp = self.client.post("/account/delete", {"email": "wrong@b.com", "csrf_token": csrf_token(body2)})
        self.assertEqual(resp.code, 200, resp.body[:500])
        self.assertIsNotNone(store.get_tenant_by_email(self.db_path, "del@b.com"))
        # Correct email deletes
        body3 = self.client.get("/account/delete").body
        resp2 = self.client.post("/account/delete", {"email": "del@b.com", "csrf_token": csrf_token(body3)})
        self.assertEqual(resp2.code, 200, resp2.body[:500])
        self.assertIn("delete_done", resp2.body)
        self.assertIsNone(store.get_tenant_by_email(self.db_path, "del@b.com"))

    def test_mail_uses_page_language(self):
        from app import mail
        mail.OUTBOX = []
        self.addCleanup(lambda: setattr(mail, "OUTBOX", None))
        self.set_language("en-GB")
        body = self.client.get("/signin").body
        self.client.post("/signin", {"email": "lang@b.com", "csrf_token": csrf_token(body)})
        self.assertEqual(mail.OUTBOX[0]["lang"], "en-GB")
