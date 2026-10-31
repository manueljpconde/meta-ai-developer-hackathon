"""Per-request interpretation context (T3).

Fail-first tests for the prompt context builder and the request
contract of the live client: the current month, the registered deal
names with their expected months, and the month-name tables with
the next-occurrence rule travel in the request, with temperature 0
and the exact one-JSON-object reply shape. The transport is stubbed,
so no test calls the network.
"""

import json
import unittest
from unittest import mock

from engine.model_client import (
    MODEL_NAME,
    MetaMoveClient,
    build_interpret_context,
)


RECORDS = [
    {"deal": "Benfica", "payment": "part-1", "month": "2026-11"},
    {"deal": "FC Porto", "payment": "part-1", "month": "2026-12"},
]


def canned_reply(text):
    """A stub urlopen returning one chat response body with text."""
    body = json.dumps(
        {"choices": [{"message": {"content": text}}]}).encode("utf-8")
    reply = mock.MagicMock()
    reply.__enter__.return_value.read.return_value = body
    return reply


def run_client(sentence, context):
    """Run the live client against a stubbed transport, capturing it."""
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["request"] = request
        captured["timeout"] = timeout
        return canned_reply(
            '{"deal": "Benfica", "payment": "part-1",'
            ' "target_month": "2027-01"}')

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        client = MetaMoveClient(api_key="test-key", context=context)
        reading = client.interpret_move(sentence)
    return reading, captured


class InterpretContextTest(unittest.TestCase):
    def test_context_names_month_deals_and_rule(self):
        context = build_interpret_context("2026-10", RECORDS)
        for expected in ("2026-10", "Benfica", "2026-11", "FC Porto",
                         "2026-12", "janeiro", "january"):
            self.assertIn(expected, context)

    def test_context_empty_without_deals(self):
        context = build_interpret_context("2026-10", [])
        self.assertIn("2026-10", context)


class RequestContractTest(unittest.TestCase):
    def test_request_carries_model_shape_and_context(self):
        reading, captured = run_client("Move the Benfica payment",
                                       "current month 2026-10")
        self.assertEqual(reading["deal"], "Benfica")
        request = captured["request"]
        self.assertTrue(request.full_url.endswith("/chat/completions"))
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], MODEL_NAME)
        self.assertEqual(payload["temperature"], 0)
        system, user = (message["content"]
                        for message in payload["messages"])
        self.assertIn("exactly one JSON object", system)
        self.assertIn("current month 2026-10", system)
        self.assertEqual(user, "Move the Benfica payment")

    def test_request_without_context_keeps_shape(self):
        reading, captured = run_client("Move the Benfica payment", "")
        self.assertEqual(reading["deal"], "Benfica")
        payload = json.loads(captured["request"].data.decode("utf-8"))
        system = payload["messages"][0]["content"]
        self.assertIn("exactly one JSON object", system)


if __name__ == "__main__":
    unittest.main()
