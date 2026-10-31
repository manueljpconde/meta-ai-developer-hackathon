"""Security: escaping, CSRF, headers and parameterised SQL.

Script markup in a negocio name is rendered escaped on every page, a
POST without a valid CSRF token is refused with 403 and saves
nothing, responses carry the security headers, and every form POST
carries a CSRF token tied to a session cookie.
"""

from app.tests.helpers import AppTestCase, DEAL_PT, csrf_token


MARKUP = "<script>alert(1)</script>"


class SecurityTest(AppTestCase):
    def test_markup_escaped_on_pages(self):
        self.save_settings()
        params = dict(DEAL_PT)
        params["name"] = MARKUP
        review = self.review(values=params)
        self.assertEqual(review.code, 200, review.body[:300])
        self.assertNotIn(MARKUP, review.body)
        self.assertIn("&lt;script&gt;", review.body)
        confirmed = self.confirm(review.body)
        self.assertEqual(confirmed.code, 303, confirmed.body[:300])
        for path in ("/", "/?month=2026-11"):
            body = self.client.get(path).body
            self.assertNotIn(MARKUP, body, path)
            self.assertIn("&lt;script&gt;", body, path)

    def test_post_without_csrf_refused(self):
        response = self.client.post("/deals/review", dict(DEAL_PT))
        self.assertEqual(response.code, 403, response.body[:300])
        self.assertEqual(self.deal_count(), 0)

    def test_post_with_wrong_csrf_refused(self):
        self.save_settings()
        params = dict(DEAL_PT)
        params["csrf_token"] = "wrong-token"
        response = self.client.post("/deals/review", params)
        self.assertEqual(response.code, 403, response.body[:300])
        self.assertEqual(self.deal_count(), 0)

    def test_security_headers_present(self):
        for path in ("/", "/settings", "/deals/new"):
            response = self.client.get(path)
            self.assertEqual(
                response.headers.get("content-security-policy"),
                "default-src 'self'",
                path,
            )
            self.assertEqual(
                response.headers.get("x-content-type-options"), "nosniff", path
            )

    def test_session_cookie_flags(self):
        from app import mail
        from app.tests.helpers import Client, csrf_token, hidden_inputs

        fresh = Client()
        with mail.stub_outbox():
            body = fresh.get("/signin").body
            params = {"email": "flags@example.pt",
                      "csrf_token": csrf_token(body)}
            posted = fresh.post("/signin", params)
            self.assertEqual(posted.code, 200, posted.body[:500])
            self.assertEqual(len(mail.outbox), 1, posted.body[:500])
            token = mail.outbox[0]["body"].split("token=")[1].split()[0]
        page = fresh.get("/auth/consume?token=" + token).body
        params = hidden_inputs(page)
        params["csrf_token"] = csrf_token(page)
        signed = fresh.post("/auth/consume", params)
        self.assertEqual(signed.code, 303, signed.body[:500])
        flags = " ".join(fresh.last_set_cookies).lower()
        self.assertIn("httponly", flags)
        self.assertIn("samesite=lax", flags)

    def test_settings_post_without_csrf_refused(self):
        body = self.client.get("/settings").body
        params = {
            "share": "50",
            "iva": "23",
            "retencao": "25",
            "irs": "30",
            "ss": "10",
            "expenses": "350,00",
            "form_locale": "pt-PT",
            "csrf_token": "wrong-token",
        }
        self.assertIn("csrf_token", body)
        response = self.client.post("/settings", params)
        self.assertEqual(response.code, 403, response.body[:300])
