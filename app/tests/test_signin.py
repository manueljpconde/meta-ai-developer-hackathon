"""Sign-in by email link: request, button-gated use, sessions.

Fail-first tests for the web sign-in flow: requesting a link
shows the same message whether or not the email has an account
and sends nothing over a rate cap; opening the link shows a
page with a Sign in button and uses nothing up; only the button
(posting the token) consumes the single-use token and starts a
30-day hashed session; expired, reused and guessed tokens sign
nobody in; without a valid session no data page renders; and
sign-out ends only that device's session. No test calls the
network.
"""

import re

from app import auth, mail, store, web
from app.tests.helpers import (
    AppTestCase,
    DEAL_PT,
    SETTINGS_PT,
    csrf_token,
    hidden_inputs,
)


def request_link(test_case, email="ana@example.pt", lang="pt-PT"):
    accept = "en-US" if lang == "en-GB" else "pt-PT"
    with mail.stub_outbox():
        body = test_case.client.get("/signin",
                                    accept_language=accept).body
        params = {"email": email, "csrf_token": csrf_token(body)}
        response = test_case.client.post("/signin", params,
                                         accept_language=accept)
        sent = list(mail.outbox)
    return response, sent


def last_token(sent):
    match = re.search(r"/auth/consume\?token=([A-Za-z0-9_\-]+)", sent["body"])
    assert match is not None, sent
    return match.group(1)


class RequestTest(AppTestCase):
    SIGNED_IN = False

    def test_request_shows_signin_page_with_email_form(self):
        body = self.client.get("/signin").body
        self.assertIn('name="email"', body)
        self.assertIn("csrf_token", body)

    def test_request_sends_link_and_shows_same_message(self):
        with mail.stub_outbox():
            body = self.client.get("/signin").body
            params = {"email": "ana@example.pt",
                      "csrf_token": csrf_token(body)}
            response = self.client.post("/signin", params)
            sent = list(mail.outbox)
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["to"], "ana@example.pt")
        self.assertIn("15", response.body)
        self.assertNotIn("token=", response.body)

    def test_unknown_email_shows_same_message(self):
        first, sent_first = request_link(self, "ana@example.pt")
        second, sent_second = request_link(self, "zul@example.pt")
        self.assertEqual(first.code, 200)
        self.assertEqual(second.code, 200)
        self.assertEqual(first.body, second.body)
        self.assertEqual(len(sent_first), 1)
        self.assertEqual(len(sent_second), 1)

    def test_request_uses_page_language(self):
        _, sent = request_link(self, lang="en-GB")
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["subject"], mail.send_subject("en-GB"))

    def test_bad_email_refused_without_sending(self):
        with mail.stub_outbox():
            body = self.client.get("/signin").body
            params = {"email": "not-an-email",
                      "csrf_token": csrf_token(body)}
            response = self.client.post("/signin", params)
            sent = list(mail.outbox)
        self.assertEqual(response.code, 200, response.body[:500])
        self.assertEqual(sent, [])
        self.assertEqual(self.deal_count_for("not-an-email"), 0)

    def test_rate_limit_refuses_without_sending(self):
        for _ in range(5):
            request_link(self, "ana@example.pt")
        response, sent = request_link(self, "ana@example.pt")
        self.assertEqual(response.code, 429, response.body[:500])
        self.assertEqual(sent, [])

    def test_request_without_csrf_refused(self):
        response = self.client.post("/signin", {"email": "ana@x.pt"})
        self.assertEqual(response.code, 403, response.body[:300])

    def deal_count_for(self, _email):
        from app import store as store_module

        tenant = store_module.tenant_by_email(self.db_path, _email)
        if tenant is None:
            return 0
        return store_module.count_deals(self.db_path, tenant=tenant)


class ConsumeTest(AppTestCase):
    SIGNED_IN = False

    def consume_token(self, token):
        body = self.client.get("/auth/consume?token=" + token).body
        params = hidden_inputs(body)
        params["csrf_token"] = csrf_token(body)
        return self.client.post("/auth/consume", params), body

    def test_opening_link_shows_button_and_uses_nothing(self):
        _, sent = request_link(self)
        token = last_token(sent[0])
        body = self.client.get("/auth/consume?token=" + token).body
        self.assertIn("Sign in", body)
        self.assertIn('type="submit"', body)
        # The link still works afterwards: opening used nothing up.
        response, _ = self.consume_token(token)
        self.assertEqual(response.code, 303, response.body[:500])

    def test_button_signs_in_and_creates_account(self):
        _, sent = request_link(self)
        token = last_token(sent[0])
        body = self.client.get("/auth/consume?token=" + token).body
        params = hidden_inputs(body)
        params["csrf_token"] = csrf_token(body)
        response = self.client.post("/auth/consume", params)
        self.assertEqual(response.code, 303, response.body[:500])
        tenant = store.tenant_by_email(self.db_path, "ana@example.pt")
        self.assertIsNotNone(tenant)
        cookies = " ".join(self.client.last_set_cookies).lower()
        self.assertIn("httponly", cookies)
        self.assertIn("samesite=lax", cookies)

    def test_second_use_signs_nobody_in(self):
        _, sent = request_link(self)
        token = last_token(sent[0])
        first, _ = self.consume_token(token)
        self.assertEqual(first.code, 303, first.body[:500])
        cookies = dict(self.client.cookies)
        other = type(self.client)()
        other.cookies = {}
        body = other.get("/auth/consume?token=" + token).body
        params = hidden_inputs(body)
        if "token" in params:
            params["csrf_token"] = csrf_token(body)
            second = other.post("/auth/consume", params)
        else:
            second = None
        self.assertTrue(second is None or second.code in (200, 400),
                        getattr(second, "body", "")[:500])
        self.assertNotEqual(dict(other.cookies).get("session"),
                            cookies.get("session"))

    def test_guessed_token_signs_nobody_in(self):
        _, sent = request_link(self)
        token = last_token(sent[0])
        _ = token
        body = self.client.get(
            "/auth/consume?token=" + auth.generate_token()).body
        params = hidden_inputs(body)
        if "token" in params:
            params["csrf_token"] = csrf_token(body)
            response = self.client.post("/auth/consume", params)
            self.assertIn(response.code, (200, 400), response.body[:500])
        home = self.client.get("/")
        self.assertNotIn("T2 Campo de Ourique", home.body)

    def test_expired_token_signs_nobody_in(self):
        raw = auth.generate_token()
        store.create_link(self.db_path, "ana@example.pt",
                          auth.hash_token(raw), "pt-PT", "127.0.0.1",
                          created_at="2026-10-31 11:00:00")
        with web.override_now("2026-10-31 12:16:00"):
            body = self.client.get("/auth/consume?token=" + raw).body
            params = hidden_inputs(body)
            if "token" in params:
                params["csrf_token"] = csrf_token(body)
                response = self.client.post("/auth/consume", params)
                self.assertIn(response.code, (200, 400),
                              response.body[:500])
        self.assertIsNone(
            store.tenant_by_email(self.db_path, "ana@example.pt"))

    def test_consume_without_csrf_refused(self):
        _, sent = request_link(self)
        token = last_token(sent[0])
        body = self.client.get("/auth/consume?token=" + token).body
        params = hidden_inputs(body)
        params["csrf_token"] = "wrong-token"
        response = self.client.post("/auth/consume", params)
        self.assertEqual(response.code, 403, response.body[:300])


class GateTest(AppTestCase):
    SIGNED_IN = False

    def test_data_pages_redirect_without_session(self):
        for path in ("/", "/settings", "/deals/new"):
            response = self.client.get(path)
            self.assertEqual(response.code, 303, path)
            self.assertIn("/signin", response.headers.get("location", ""))

    def test_posts_redirect_without_session(self):
        response = self.client.post("/settings", dict(SETTINGS_PT))
        self.assertEqual(response.code, 303)
        self.assertIn("/signin", response.headers.get("location", ""))

    def test_signed_in_agent_reaches_pages(self):
        _, sent = request_link(self)
        token = last_token(sent[0])
        body = self.client.get("/auth/consume?token=" + token).body
        params = hidden_inputs(body)
        params["csrf_token"] = csrf_token(body)
        signed = self.client.post("/auth/consume", params)
        self.assertEqual(signed.code, 303, signed.body[:500])
        for path in ("/", "/settings", "/deals/new"):
            response = self.client.get(path)
            self.assertEqual(response.code, 200, path)

    def test_sign_out_ends_only_this_device(self):
        self.signin("ana@example.pt")
        from app.tests.helpers import Client

        other = Client()
        with mail.stub_outbox():
            body = other.get("/signin").body
            params = {"email": "ana@example.pt",
                      "csrf_token": csrf_token(body)}
            posted = other.post("/signin", params)
            self.assertEqual(posted.code, 200, posted.body[:500])
            match = re.search(r"token=([A-Za-z0-9_\-]+)",
                              mail.outbox[0]["body"])
            self.assertIsNotNone(match, mail.outbox[0]["body"])
            token = match.group(1)
        page = other.get("/auth/consume?token=" + token).body
        params = hidden_inputs(page)
        params["csrf_token"] = csrf_token(page)
        signed = other.post("/auth/consume", params)
        self.assertEqual(signed.code, 303, signed.body[:500])
        first = self.client.get("/signout").body
        params = {"csrf_token": csrf_token(first)}
        left = self.client.post("/signout", params)
        self.assertEqual(left.code, 303, left.body[:500])
        home = self.client.get("/")
        self.assertEqual(home.code, 303)
        still = other.get("/")
        self.assertEqual(still.code, 200)

    def test_expired_session_sees_no_data(self):
        _, sent = request_link(self)
        token = last_token(sent[0])
        body = self.client.get("/auth/consume?token=" + token).body
        params = hidden_inputs(body)
        params["csrf_token"] = csrf_token(body)
        signed = self.client.post("/auth/consume", params)
        self.assertEqual(signed.code, 303)
        tenant = store.tenant_by_email(self.db_path, "ana@example.pt")
        cookies = dict(self.client.cookies)
        raw_session = cookies.get("session", "")
        digest = auth.hash_token(raw_session)
        conn_holder = __import__("sqlite3").connect(self.db_path)
        try:
            conn_holder.execute(
                "UPDATE sessions SET created_at = ? WHERE session_hash = ?",
                ("2026-09-01 12:00:00", digest),
            )
            conn_holder.commit()
        finally:
            conn_holder.close()
        home = self.client.get("/")
        self.assertEqual(home.code, 303)


class IsolationWebTest(AppTestCase):
    def test_cross_tenant_deal_id_yields_no_data(self):
        self.signin("ana@example.pt")
        self.save_settings()
        review = self.review()
        self.assertEqual(review.code, 200, review.body[:300])
        confirmed = self.confirm(review.body)
        self.assertEqual(confirmed.code, 303, confirmed.body[:300])
        tenant = store.tenant_by_email(self.db_path, "ana@example.pt")
        ident = store.list_deals(self.db_path, tenant=tenant)[0]["id"]
        from app.tests.helpers import Client

        other = Client()
        with mail.stub_outbox():
            body = other.get("/signin").body
            params = {"email": "bruno@example.pt",
                      "csrf_token": csrf_token(body)}
            posted = other.post("/signin", params)
            self.assertEqual(posted.code, 200, posted.body[:500])
            match = re.search(r"token=([A-Za-z0-9_\-]+)",
                              mail.outbox[0]["body"])
            self.assertIsNotNone(match, mail.outbox[0]["body"])
            token = match.group(1)
        body = other.get("/auth/consume?token=" + token).body
        params = hidden_inputs(body)
        params["csrf_token"] = csrf_token(body)
        signed = other.post("/auth/consume", params)
        self.assertEqual(signed.code, 303, signed.body[:500])
        home = other.get("/")
        self.assertNotIn("T2 Campo de Ourique", home.body)
        missing = other.get("/deals/%d" % ident)
        self.assertIn(missing.code, (303, 404), missing.body[:500])
        self.assertNotIn("T2 Campo de Ourique", missing.body)

    def test_deal_form_defaults_to_signed_in_settings(self):
        self.signin("ana@example.pt")
        self.save_settings()
        form = self.client.get("/deals/new").body
        self.assertIn("50", form)


if __name__ == "__main__":
    import unittest

    unittest.main()
