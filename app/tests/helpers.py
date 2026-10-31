"""Shared harness for the acceptance tests.

Drives the WSGI application directly, with one temporary database per
test. The database path is injected through ``web.DB_PATH`` so no
server process is needed. Every case signs in through the real
email-link flow (with the stub outbox, so no test touches the
network) unless it opts out with ``SIGNED_IN = False``.
"""

import io
import re
import tempfile
import unittest
import urllib.parse

from app import mail, store, web


SETTINGS_PT = {
    "share": "50",
    "iva": "23",
    "retencao": "25",
    "irs": "30",
    "ss": "10",
    "expenses": "350,00",
    "form_locale": "pt-PT",
}

SETTINGS_EN = {
    "share": "50",
    "iva": "23",
    "retencao": "25",
    "irs": "30",
    "ss": "10",
    "expenses": "350.00",
    "form_locale": "en-GB",
}

DEAL_PT = {
    "name": "T2 Campo de Ourique",
    "commission": "10000,00",
    "share": "50",
    "month": "2026-11",
    "stage": "confirmado",
    "agency": "Imo Lisboa",
    "form_locale": "pt-PT",
}

DEAL_EN = {
    "name": "T2 Campo de Ourique",
    "commission": "10000.00",
    "share": "50",
    "month": "2026-11",
    "stage": "confirmado",
    "agency": "Imo Lisboa",
    "form_locale": "en-GB",
}


class Response:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body

    @property
    def code(self):
        return int(self.status.split()[0])


class Client:
    """Minimal WSGI client with a cookie jar."""

    def __init__(self):
        self.cookies = {}
        self.accept_language = None
        self.last_set_cookies = []

    def request(self, method, path, params=None, accept_language=None):
        if "?" in path:
            path_info, query = path.split("?", 1)
        else:
            path_info, query = path, ""
        raw = b""
        if params is not None:
            raw = urllib.parse.urlencode(params).encode("utf-8")
        env = {
            "REQUEST_METHOD": method,
            "SCRIPT_NAME": "",
            "PATH_INFO": path_info,
            "QUERY_STRING": query,
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
            "CONTENT_LENGTH": str(len(raw)),
            "wsgi.input": io.BytesIO(raw),
            "wsgi.url_scheme": "http",
            "SERVER_NAME": "localhost",
            "SERVER_PORT": "8000",
        }
        if self.cookies:
            env["HTTP_COOKIE"] = "; ".join(
                "%s=%s" % item for item in sorted(self.cookies.items())
            )
        language = accept_language if accept_language is not None else self.accept_language
        if language is not None:
            env["HTTP_ACCEPT_LANGUAGE"] = language
        captured = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = headers

        chunks = web.application(env, start_response)
        body = b"".join(chunks)
        if hasattr(chunks, "close"):
            chunks.close()
        headers = {}
        set_cookies = []
        for name, value in captured["headers"]:
            key = name.lower()
            if key == "set-cookie":
                set_cookies.append(value)
                part = value.split(";", 1)[0]
                if "=" in part:
                    name_, value_ = part.split("=", 1)
                    self.cookies[name_.strip()] = value_.strip()
            elif key in headers:
                headers[key] = headers[key] + "\n" + value
            else:
                headers[key] = value
        self.last_set_cookies = set_cookies
        return Response(captured["status"], headers, body.decode("utf-8"))

    def get(self, path, accept_language=None):
        return self.request("GET", path, accept_language=accept_language)

    def post(self, path, params, accept_language=None):
        return self.request("POST", path, params=params,
                            accept_language=accept_language)


def hidden_inputs(body):
    """Map of hidden input names to values in an HTML page."""
    found = {}
    for match in re.finditer(r'<input[^>]*type="hidden"[^>]*>', body):
        tag = match.group(0)
        name = re.search(r'name="([^"]+)"', tag)
        value = re.search(r'value="([^"]*)"', tag)
        if name is not None:
            found[name.group(1)] = value.group(1) if value is not None else ""
    return found


def csrf_token(body):
    return hidden_inputs(body)["csrf_token"]


class AppTestCase(unittest.TestCase):
    SIGNED_IN = True

    SIGNIN_EMAIL = "ana@example.pt"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = tmp.name + "/test.db"
        web.DB_PATH = self.db_path
        self.client = Client()
        self.signed_in_email = None
        if self.SIGNED_IN:
            self.signin(self.SIGNIN_EMAIL)

    def signin(self, email=None):
        """Sign in through the real link flow, mail stubbed."""
        if self.client.cookies.get("session"):
            return None
        address = email or self.SIGNIN_EMAIL
        with mail.stub_outbox():
            body = self.client.get("/signin").body
            params = {"email": address, "csrf_token": csrf_token(body)}
            response = self.client.post("/signin", params)
            self.assertEqual(response.code, 200, response.body[:500])
            self.assertEqual(len(mail.outbox), 1, response.body[:500])
            match = re.search(r"token=([A-Za-z0-9_\-]+)",
                              mail.outbox[0]["body"])
            self.assertIsNotNone(match, mail.outbox[0]["body"])
            token = match.group(1)
        page = self.client.get("/auth/consume?token=" + token).body
        params = hidden_inputs(page)
        params["csrf_token"] = csrf_token(page)
        signed = self.client.post("/auth/consume", params)
        self.assertEqual(signed.code, 303, signed.body[:500])
        self.signed_in_email = address
        return signed

    def deal_count(self):
        email = self.signed_in_email or self.SIGNIN_EMAIL
        tenant = store.tenant_by_email(self.db_path, email)
        if tenant is None:
            return 0
        return store.count_deals(self.db_path, tenant=tenant)

    @property
    def tenant(self):
        """Signed-in tenant id for tenant-scoped store calls."""
        email = self.signed_in_email or self.SIGNIN_EMAIL
        ident = store.tenant_by_email(self.db_path, email)
        assert ident is not None, "no tenant for %r" % email
        return ident

    def stored_deals(self, month=None):
        """Deals of the signed-in tenant, optionally for one month."""
        return store.list_deals(self.db_path, month, tenant=self.tenant)

    def stored_settings(self):
        """Settings of the signed-in tenant."""
        return store.get_settings(self.db_path, tenant=self.tenant)

    def set_language(self, lang):
        body = self.client.get("/").body
        if "csrf_token" not in body:
            body = self.client.get("/signin").body
        params = {"lang": lang, "csrf_token": csrf_token(body)}
        response = self.client.post("/language", params)
        self.assertEqual(response.code, 303, response.body[:500])
        return response

    def save_settings(self, values=None):
        body = self.client.get("/settings").body
        params = dict(SETTINGS_PT if values is None else values)
        params["csrf_token"] = csrf_token(body)
        response = self.client.post("/settings", params)
        self.assertEqual(response.code, 303, response.body[:500])
        return response

    def deal_params(self, lang, **overrides):
        params = dict(DEAL_EN if lang == "en-GB" else DEAL_PT)
        params.update(overrides)
        params["form_locale"] = lang
        return params

    def review(self, values=None, lang="pt-PT"):
        body = self.client.get("/deals/new").body
        if values is None:
            params = self.deal_params(lang)
        else:
            params = dict(values)
        params["csrf_token"] = csrf_token(body)
        return self.client.post("/deals/review", params)

    def confirm(self, review_body, csrf=None):
        params = hidden_inputs(review_body)
        if csrf is None:
            params["csrf_token"] = csrf_token(review_body)
        else:
            params["csrf_token"] = csrf
        return self.client.post("/deals/confirm", params)
