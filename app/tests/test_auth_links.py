"""Email-link sign-up and sign-in: hashing, single use, 15-minute expiry."""

import hashlib
import time
import tempfile
import unittest

from app import store, auth


class TokenHashTest(unittest.TestCase):
    def test_token_hashed_not_stored_raw(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = tmp.name + "/test.db"
        token = "raw-token-abc"
        auth.request_link(path, "a@b.com", "1.2.3.4", lang="en-GB", now=1000.0, token=token)
        rows = store.list_login_links(path)
        self.assertEqual(len(rows), 1)
        self.assertNotEqual(rows[0]["token_hash"], token)
        self.assertEqual(rows[0]["token_hash"], hashlib.sha256(token.encode()).hexdigest())

    def test_verify_accepts_valid_link(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = tmp.name + "/test.db"
        token = "tok-valid"
        auth.request_link(path, "a@b.com", "1.2.3.4", lang="en-GB", now=1000.0, token=token)
        result = auth.verify_link(path, token, now=1000.0 + 60)
        self.assertIsNotNone(result)
        self.assertEqual(result["email"], "a@b.com")

    def test_single_use(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = tmp.name + "/test.db"
        token = "tok-once"
        auth.request_link(path, "a@b.com", "1.2.3.4", lang="en-GB", now=1000.0, token=token)
        first = auth.verify_link(path, token, now=1000.0 + 60)
        self.assertIsNotNone(first)
        second = auth.verify_link(path, token, now=1000.0 + 120)
        self.assertIsNone(second)

    def test_expiry_15_minutes(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = tmp.name + "/test.db"
        token = "tok-exp"
        auth.request_link(path, "a@b.com", "1.2.3.4", lang="en-GB", now=1000.0, token=token)
        # 14 minutes OK
        ok = auth.verify_link(path, token, now=1000.0 + 14 * 60)
        self.assertIsNotNone(ok)
        # need fresh token for expiry test (previous was consumed)
        token2 = "tok-exp2"
        auth.request_link(path, "x@y.com", "1.2.3.4", lang="en-GB", now=2000.0, token=token2)
        expired = auth.verify_link(path, token2, now=2000.0 + 16 * 60)
        self.assertIsNone(expired)

    def test_guessed_token_yields_nothing(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = tmp.name + "/test.db"
        auth.request_link(path, "a@b.com", "1.2.3.4", lang="en-GB", now=1000.0, token="real")
        result = auth.verify_link(path, "guessed-random", now=1000.0 + 10)
        self.assertIsNone(result)

    def test_first_valid_link_creates_tenant(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = tmp.name + "/test.db"
        token = "tok-new-tenant"
        auth.request_link(path, "new@b.com", "1.2.3.4", lang="en-GB", now=1000.0, token=token)
        self.assertIsNone(store.get_tenant_by_email(path, "new@b.com"))
        auth.verify_link(path, token, now=1000.0 + 10)
        self.assertIsNotNone(store.get_tenant_by_email(path, "new@b.com"))

    def test_expired_link_does_not_create_tenant(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = tmp.name + "/test.db"
        token = "tok-exp-no-create"
        auth.request_link(path, "new2@b.com", "1.2.3.4", lang="en-GB", now=1000.0, token=token)
        result = auth.verify_link(path, token, now=1000.0 + 20 * 60)
        self.assertIsNone(result)
        self.assertIsNone(store.get_tenant_by_email(path, "new2@b.com"))
