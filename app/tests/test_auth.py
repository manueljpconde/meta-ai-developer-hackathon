"""Sign-in token, session and rate-limit helpers (stdlib only).

Fail-first tests for ``app.auth``: email normalization and
validation, random single-use token hashing (never the raw token),
link expiry of 15 minutes, fixed 30-day sessions, per-email and
per-IP rate caps, and proxy-aware client addresses. No test calls
the network.
"""

import unittest
from datetime import datetime, timedelta, timezone

from app import auth


NOW = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)


class EmailTest(unittest.TestCase):
    def test_normalizes_case_and_spaces(self):
        self.assertEqual(
            auth.normalize_email("  Ana@Example.PT "), "ana@example.pt"
        )

    def test_accepts_plain_address(self):
        self.assertTrue(auth.valid_email("ana@example.pt"))

    def test_refuses_without_at(self):
        self.assertFalse(auth.valid_email("ana.example.pt"))

    def test_refuses_blank(self):
        self.assertFalse(auth.valid_email("   "))

    def test_refuses_spaces_inside(self):
        self.assertFalse(auth.valid_email("a na@example.pt"))


class TokenTest(unittest.TestCase):
    def test_tokens_are_random_and_url_safe(self):
        first = auth.generate_token()
        second = auth.generate_token()
        self.assertNotEqual(first, second)
        self.assertTrue(first)
        self.assertNotIn("+", first)
        self.assertNotIn("/", first)

    def test_hash_is_stable_and_hides_the_token(self):
        raw = auth.generate_token()
        first = auth.hash_token(raw)
        self.assertEqual(first, auth.hash_token(raw))
        self.assertNotIn(raw, first)
        self.assertEqual(len(first), 64)

    def test_distinct_tokens_hash_distinctly(self):
        self.assertNotEqual(
            auth.hash_token(auth.generate_token()),
            auth.hash_token(auth.generate_token()),
        )


class LinkExpiryTest(unittest.TestCase):
    def test_link_lives_fifteen_minutes(self):
        created = NOW
        self.assertTrue(auth.link_valid(created, NOW + timedelta(minutes=14)))
        self.assertFalse(auth.link_valid(created, NOW + timedelta(minutes=16)))

    def test_boundary_is_fifteen_minutes(self):
        created = NOW
        self.assertTrue(
            auth.link_valid(created, created + timedelta(minutes=15))
        )
        self.assertFalse(
            auth.link_valid(
                created, created + timedelta(minutes=15, seconds=1)
            )
        )


class SessionExpiryTest(unittest.TestCase):
    def test_session_lives_thirty_days_from_sign_in(self):
        created = NOW
        self.assertTrue(
            auth.session_valid(created, created + timedelta(days=29))
        )
        self.assertFalse(
            auth.session_valid(created, created + timedelta(days=30, seconds=1))
        )

    def test_visits_do_not_extend_the_session(self):
        created = NOW
        later = created + timedelta(days=29)
        self.assertTrue(auth.session_valid(created, later))
        self.assertFalse(
            auth.session_valid(created, created + timedelta(days=31))
        )


class RateLimitTest(unittest.TestCase):
    def test_email_cap_allows_five_then_refuses(self):
        counts = [0]
        for _ in range(5):
            self.assertTrue(auth.email_allowed(counts[0]))
            counts[0] += 1
        self.assertFalse(auth.email_allowed(counts[0]))

    def test_ip_cap_allows_twenty_then_refuses(self):
        for count in range(20):
            self.assertTrue(auth.ip_allowed(count))
        self.assertFalse(auth.ip_allowed(20))

    def test_caps_are_named(self):
        self.assertEqual(auth.EMAIL_LIMIT, 5)
        self.assertEqual(auth.IP_LIMIT, 20)


class ClientAddressTest(unittest.TestCase):
    def test_socket_address_without_proxy(self):
        env = {"REMOTE_ADDR": "203.0.113.7"}
        self.assertEqual(auth.client_ip(env), "203.0.113.7")

    def test_forwarded_header_ignored_without_proxy(self):
        env = {
            "REMOTE_ADDR": "203.0.113.7",
            "HTTP_X_FORWARDED_FOR": "198.51.100.9",
        }
        self.assertEqual(auth.client_ip(env), "203.0.113.7")

    def test_forwarded_header_used_behind_caddy(self):
        env = {
            "REMOTE_ADDR": "127.0.0.1",
            "HTTP_X_FORWARDED_FOR": "198.51.100.9, 10.0.0.1",
        }
        self.assertEqual(auth.client_ip(env), "198.51.100.9")

    def test_missing_remote_addr_falls_back(self):
        self.assertEqual(auth.client_ip({}), "unknown")


if __name__ == "__main__":
    unittest.main()
