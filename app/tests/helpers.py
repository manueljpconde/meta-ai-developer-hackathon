"""Shared harness for the section 3 acceptance tests.

Drives the WSGI application directly, with one temporary database per
test. The database path is injected through ``web.DB_PATH`` so no
server process is needed.
"""

import io
import re
import tempfile
import unittest
import urllib.parse

from app import web


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

        def start_response(status, headers, exc_info=None):
            if captured:
                raise AssertionError("Headers already set!")
            captured["status"] = status
            captured["headers"] = headers
            def write(data):
                raise AssertionError("Headers already set!")
            return write

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

    def post(self, path, params):
        return self.request("POST", path, params=params)


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
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = tmp.name + "/test.db"
        web.DB_PATH = self.db_path
        self.client = Client()
        self._authenticate_for_tests()

    def _authenticate_for_tests(self):
        from app import auth as _auth, store as _store
        import time as _time
        email = "test@example.com"
        _store.get_or_create_tenant(self.db_path, email, now=_time.time())
        tenant = _store.get_tenant_by_email(self.db_path, email)
        sid = "test-session-" + tenant["email"]
        # Use store directly to avoid rate limit noise
        import secrets as _secrets
        csrf = _secrets.token_urlsafe(16)
        _store.create_session(self.db_path, sid, tenant["id"], email, _time.time(), _time.time() + 3600*24*30, csrf)
        self.client.cookies["session"] = sid

    def _unauthenticate(self):
        self.client.cookies.pop("session", None)


    def deal_count(self):
        from app import store

        return store.count_deals(self.db_path)

    def set_language(self, lang):
        # Use /signin (public) to get CSRF when not authenticated
        body = self.client.get("/signin").body
        if "csrf_token" not in body:
            body = self.client.get("/").body
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
