"""Owner request 2026-11-04: an email to the owner whenever an Agentimo account is created."""
import os
import tempfile
import unittest
from unittest import mock

from app import auth, mail, web
from app.tests.helpers import Client, open_link


class NewAccountNoticeTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = tmp.name + "/test.db"
        web.DB_PATH = self.db_path
        mail.OUTBOX = []
        self.addCleanup(lambda: setattr(mail, "OUTBOX", None))
        old = os.environ.get("OWNER_NOTIFY_EMAIL")
        os.environ["OWNER_NOTIFY_EMAIL"] = "owner@example.com"
        self.addCleanup(lambda: os.environ.__setitem__("OWNER_NOTIFY_EMAIL", old) if old is not None
                        else os.environ.pop("OWNER_NOTIFY_EMAIL", None))

    def sign_in(self, email):
        ok, token = auth.request_link(self.db_path, email, "9.9.9.%d" % len(mail.OUTBOX), lang="pt-PT")
        self.assertTrue(ok)
        return open_link(Client(), token)

    def notices(self):
        return [m for m in mail.OUTBOX if m["to"] == "owner@example.com"]

    def test_a_new_account_sends_the_owner_one_notice_with_its_email(self):
        self.assertEqual(self.sign_in("New.Agent@Example.com").code, 303)
        [notice] = self.notices()
        self.assertIn("new.agent@example.com", notice["subject"] + notice["body"])

    def test_signing_in_again_to_an_existing_account_sends_nothing(self):
        self.sign_in("agent@example.com")
        self.sign_in("agent@example.com")
        self.assertEqual(len(self.notices()), 1)

    def test_a_failed_notice_never_blocks_sign_in(self):
        with mock.patch.object(mail, "send_new_account_notice", side_effect=OSError("relay down")):
            response = self.sign_in("agent@example.com")
        self.assertEqual(response.code, 303, "the sign-in still completes")
        from app import store
        self.assertIsNotNone(store.get_tenant_by_email(self.db_path, "agent@example.com"))

    def test_without_an_owner_address_nothing_is_sent(self):
        os.environ.pop("OWNER_NOTIFY_EMAIL")
        self.sign_in("agent@example.com")
        self.assertEqual(self.notices(), [])


if __name__ == "__main__":
    unittest.main()
