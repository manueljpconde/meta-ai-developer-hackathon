"""Session gate: every route requires sign-in except explicit public list; enumeration test."""

import unittest
from app.tests.helpers import AppTestCase
from app import web
from app.tests.helpers import Client


class RouteEnumerationTest(AppTestCase):
    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        web.DB_PATH = self._tmp.name + "/test.db"
        self.client = Client()  # no session
        # Need at least one tenant for auth to resolve but client is unauthenticated
        from app import store as _s
        import time
        _s.get_or_create_tenant(web.DB_PATH, "x@y.com", now=time.time())

    def _code(self, path, method="GET", params=None):
        if method == "GET":
            resp = self.client.get(path)
        else:
            # need csrf for POST that is gated before csrf; unauthenticated POST should redirect before csrf check
            resp = self.client.request(method, path, params=params or {})
        return resp.code, resp

    def test_every_non_public_route_redirects(self):
        public = set(web.PUBLIC_ROUTES) | {"/static/style.css"}  # stylesheet is public per spec
        for path, method in web.APP_ROUTES:
            if path in public or path.startswith("/static/"):
                continue
            code, resp = self._code(path, method)
            self.assertIn(code, (302, 303), "route %s %s should redirect (got %d)" % (method, path, code))
            self.assertIn("/signin", resp.headers.get("location", ""), "route %s %s should redirect to signin" % (method, path))

    def test_public_routes_do_not_redirect(self):
        for path, method in web.APP_ROUTES:
            if path not in web.PUBLIC_ROUTES and not path.startswith("/static/"):
                continue
            # public should not redirect to signin
            code, resp = self._code(path, method if method == "GET" else "GET")
            self.assertNotIn("/signin", resp.headers.get("location", ""), "public %s should not redirect to signin" % path)

    def test_unknown_route_still_gated(self):
        code, resp = self._code("/unknown-route-xyz", "GET")
        self.assertIn(code, (302, 303, 404))
        if code in (302, 303):
            self.assertIn("/signin", resp.headers.get("location", ""))

    def test_session_hash_at_rest(self):
        from app import store, auth
        import tempfile, time, hashlib, sqlite3
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = tmp.name + "/test.db"
        auth.request_link(path, "h@h.com", "1.1.1.1", now=1000.0, token="tok-hash-check")
        link = auth.verify_link(path, "tok-hash-check", now=1010.0)
        sess = auth.create_session_for_link(path, link, now=1010.0)
        raw_id = sess["id"]
        # raw token should not appear in DB
        conn = sqlite3.connect(path)
        rows = conn.execute("SELECT id FROM sessions").fetchall()
        conn.close()
        stored_ids = [r[0] for r in rows]
        self.assertNotIn(raw_id, stored_ids)
        # stored is hash
        self.assertIn(hashlib.sha256(raw_id.encode()).hexdigest(), stored_ids)
