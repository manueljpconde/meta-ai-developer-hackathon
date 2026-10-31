"""Sign-in mail through the PropWare relay, stubbed in tests.

Fail-first tests for ``app.mail``: the message goes to the given
address from the configured sender, the body and subject follow the
page language at request time, the link carries the raw token once,
and nothing ever leaves the test run (the stub outbox records the
message instead of opening a socket). No test calls the network.
"""

import unittest
from unittest import mock

from app import mail


class OutboxTest(unittest.TestCase):
    def setUp(self):
        self.stubbed = mail.stub_outbox()
        self.stubbed.__enter__()
        self.addCleanup(self.stubbed.__exit__, None, None, None)

    def test_message_recorded_in_portuguese(self):
        mail.send_signin_link(
            "ana@example.pt", "https://app.example/link?t=abc", "pt-PT"
        )
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message["to"], "ana@example.pt")
        self.assertIn("abc", message["body"])
        self.assertTrue(message["subject"])

    def test_message_recorded_in_english(self):
        mail.send_signin_link(
            "ana@example.pt", "https://app.example/link?t=abc", "en-GB"
        )
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertNotEqual(
            message["subject"],
            mail.send_subject("pt-PT"),
        )

    def test_no_socket_opened_while_stubbed(self):
        with mock.patch("smtplib.SMTP") as smtp:
            mail.send_signin_link(
                "ana@example.pt", "https://app.example/link?t=abc", "pt-PT"
            )
            smtp.assert_not_called()
        self.assertEqual(len(mail.outbox), 1)

    def test_token_never_logged(self):
        with mock.patch.object(mail, "logger") as logger:
            mail.send_signin_link(
                "ana@example.pt", "https://app.example/link?t=secret", "pt-PT"
            )
        for call in logger.method_calls:
            for arg in call.args:
                self.assertNotIn("secret", str(arg))


class SettingsTest(unittest.TestCase):
    def test_defaults_name_the_propware_relay(self):
        settings = mail.smtp_settings({})
        self.assertEqual(settings["host"], "smtp-relay.gmail.com")
        self.assertEqual(settings["sender"], "hello@propware.pt")

    def test_environment_overrides(self):
        settings = mail.smtp_settings({
            "APP_SMTP_HOST": "relay.example",
            "APP_SMTP_PORT": "2525",
            "APP_SMTP_USER": "user",
            "APP_SMTP_PASS": "pass",
            "APP_MAIL_SENDER": "ola@example.pt",
        })
        self.assertEqual(settings["host"], "relay.example")
        self.assertEqual(settings["port"], 2525)
        self.assertEqual(settings["username"], "user")
        self.assertEqual(settings["password"], "pass")
        self.assertEqual(settings["sender"], "ola@example.pt")


if __name__ == "__main__":
    unittest.main()
