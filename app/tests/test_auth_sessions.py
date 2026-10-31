"""Rate limiting per email and per IP."""

import tempfile
import unittest

from app import auth
from app import store


class RateLimitEmailTest(unittest.TestCase):
    def test_per_email_limit_refuses_after_cap(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = tmp.name + "/test.db"
        # 5 requests OK
        for i in range(5):
            ok, _ = auth.request_link(path, "a@b.com", "1.1.1.1", now=1000.0 + i, token="tok%d" % i)
            self.assertTrue(ok, i)
        # 6th refused
        ok, err = auth.request_link(path, "a@b.com", "1.1.1.1", now=1010.0, token="tok5")
        self.assertFalse(ok)
        self.assertEqual(err, "err_rate_email")

    def test_per_ip_limit_refuses_after_cap(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = tmp.name + "/test.db"
        for i in range(20):
            ok, _ = auth.request_link(path, "user%d@b.com" % i, "9.9.9.9", now=1000.0 + i, token="iptok%d" % i)
            self.assertTrue(ok, i)
        ok, err = auth.request_link(path, "extra@b.com", "9.9.9.9", now=1100.0, token="iptok20")
        self.assertFalse(ok)
        self.assertEqual(err, "err_rate_ip")

    def test_different_ips_not_limited(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = tmp.name + "/test.db"
        ok, _ = auth.request_link(path, "a@b.com", "1.1.1.1", now=1000.0, token="t1")
        self.assertTrue(ok)
        ok, _ = auth.request_link(path, "a@b.com", "2.2.2.2", now=1001.0, token="t2")
        self.assertTrue(ok)

    def test_rate_limit_survives_restart(self):
        # DB-backed, so same path
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = tmp.name + "/test.db"
        for i in range(5):
            auth.request_link(path, "a@b.com", "1.1.1.1", now=1000.0 + i, token="r%d" % i)
        ok, _ = auth.request_link(path, "a@b.com", "1.1.1.1", now=1010.0, token="r5")
        self.assertFalse(ok)


class SessionTest(unittest.TestCase):
    def test_session_valid_and_expiry_fixed_30_days(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = tmp.name + "/test.db"
        token = "tok-sess"
        auth.request_link(path, "u@v.com", "1.2.3.4", now=1000.0, token=token)
        link = auth.verify_link(path, token, now=1010.0)
        sess = auth.create_session_for_link(path, link, now=1010.0)
        # valid within 30 days
        found = auth.get_valid_session(path, sess["id"], now=1010.0 + 29 * 24 * 3600)
        self.assertIsNotNone(found)
        self.assertEqual(found["email"], "u@v.com")
        # expired after 30 days
        expired = auth.get_valid_session(path, sess["id"], now=1010.0 + 31 * 24 * 3600)
        self.assertIsNone(expired)

    def test_session_not_extended_by_visits(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = tmp.name + "/test.db"
        token = "tok-sess2"
        auth.request_link(path, "u2@v.com", "1.2.3.4", now=1000.0, token=token)
        link = auth.verify_link(path, token, now=1010.0)
        sess = auth.create_session_for_link(path, link, now=1010.0)
        # visiting at 15 days does not extend
        auth.get_valid_session(path, sess["id"], now=1010.0 + 15 * 24 * 3600)
        expired = auth.get_valid_session(path, sess["id"], now=1010.0 + 31 * 24 * 3600)
        self.assertIsNone(expired)

    def test_sign_out_ends_only_that_session(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = tmp.name + "/test.db"
        for i in range(2):
            tok = "tok-dev%d" % i
            auth.request_link(path, "same@v.com", "1.2.3.4", now=1000.0 + i * 10, token=tok)
            link = auth.verify_link(path, tok, now=1010.0 + i * 10)
            if i == 0:
                sess0 = auth.create_session_for_link(path, link, now=1010.0)
            else:
                sess1 = auth.create_session_for_link(path, link, now=1020.0)
        store.delete_session(path, sess0["id"])
        self.assertIsNone(auth.get_valid_session(path, sess0["id"], now=1030.0))
        self.assertIsNotNone(auth.get_valid_session(path, sess1["id"], now=1030.0))

    def test_hashed_session_id(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = tmp.name + "/test.db"
        token = "tok-hash-sess"
        auth.request_link(path, "h@v.com", "1.2.3.4", now=1000.0, token=token)
        link = auth.verify_link(path, token, now=1010.0)
        sess = auth.create_session_for_link(path, link, now=1010.0)
        stored = store.get_session(path, sess["id"])
        self.assertIsNotNone(stored)
        # session id is random urlsafe, not derived from email
        self.assertNotIn("h@v.com", sess["id"])
