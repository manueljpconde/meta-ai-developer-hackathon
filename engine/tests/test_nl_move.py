"""Natural-language move input: sentence to structured move.

Fail-first tests for turning a typed sentence such as "Move the
Benfica payment to January" into a structured move handled by
``engine.move.move_payment`` and shown as a before/after forecast.
Interpretation runs through a fake client, so no test calls the
network: a clear move, an ambiguous sentence, an unknown deal and a
model failure. Stored records are never changed.
"""

import copy
import os
import unittest
from unittest import mock

from engine.model_client import (
    API_KEY_ENV_VAR,
    MODEL_NAME,
    MetaMoveClient,
    ModelError,
    MoveModelClient,
)
from engine.nl_move import plan_nl_move


STANDARD_RATES = {
    "iva_rate": "0.23",
    "retencao_rate": "0.25",
    "irs_rate": "0.30",
    "ss_rate": "0.10",
}

CURRENT = "2026-10"
SOURCE = "2026-11"
TARGET = "2027-01"
SENTENCE = "Move the Benfica payment to January"


def record(deal, payment, month, base, received=False, rates=None):
    """Build one payment record with the standard rates unless given."""
    entry = {
        "deal": deal,
        "payment": payment,
        "month": month,
        "part_base": base,
        "received": received,
    }
    entry.update(STANDARD_RATES if rates is None else rates)
    return entry


def example_records():
    """Two unpaid November payments: Benfica and a smaller zero-rate one."""
    return [
        record("Benfica", "part-1", SOURCE, 500000),
        record("FC Porto", "part-1", SOURCE, 320000, rates={}),
    ]


def fake_interpret(result=None, error=None):
    """A fake interpretation client recording the sentences it sees."""
    def run(sentence):
        run.seen.append(sentence)
        if error is not None:
            raise error
        if isinstance(result, dict):
            return dict(result)
        return result
    run.seen = []
    return run


def clear_move():
    return {
        "deal": "Benfica",
        "payment": "part-1",
        "target_month": TARGET,
    }


class ClearMoveTest(unittest.TestCase):
    def test_clear_sentence_moves_and_shows_before_and_after(self):
        interpret = fake_interpret(result=clear_move())
        outcome = plan_nl_move(SENTENCE, example_records(), CURRENT,
                               interpret)
        self.assertEqual(interpret.seen, [SENTENCE])
        self.assertEqual(outcome["status"], "moved")
        self.assertEqual(
            outcome["moved"],
            {
                "deal": "Benfica",
                "payment": "part-1",
                "from_month": SOURCE,
                "target_month": TARGET,
            },
        )
        self.assertEqual(outcome["before"][SOURCE]["commission"], 820000)
        self.assertEqual(outcome["after"][SOURCE]["commission"], 320000)
        self.assertEqual(outcome["after"][TARGET]["commission"], 500000)

    def test_before_and_after_figures_match_engine(self):
        outcome = plan_nl_move(SENTENCE, example_records(), CURRENT,
                               fake_interpret(result=clear_move()))
        self.assertEqual(outcome["before"][SOURCE]["really_available"],
                         620000)
        self.assertEqual(outcome["after"][TARGET]["really_available"],
                         300000)
        self.assertEqual(outcome["after"][SOURCE]["really_available"],
                         320000)

    def test_records_unchanged(self):
        records = example_records()
        snapshot = copy.deepcopy(records)
        plan_nl_move(SENTENCE, records, CURRENT,
                     fake_interpret(result=clear_move()))
        self.assertEqual(records, snapshot)


class AmbiguousSentenceTest(unittest.TestCase):
    def test_ambiguous_sentence_asks_one_question(self):
        records = example_records()
        records.append(record("Benfica", "part-1", "2026-12", 500000))
        interpret = fake_interpret(result={
            "question": "Which Benfica payment did you mean?",
        })
        outcome = plan_nl_move("Move the Benfica payment", records,
                               CURRENT, interpret)
        self.assertEqual(outcome["status"], "question")
        self.assertEqual(outcome["question"],
                         "Which Benfica payment did you mean?")
        self.assertNotIn("after", outcome)

    def test_duplicate_records_ask_instead_of_guessing(self):
        records = example_records()
        records.append(record("Benfica", "part-1", "2026-12", 500000))
        outcome = plan_nl_move(SENTENCE, records, CURRENT,
                               fake_interpret(result=clear_move()))
        self.assertEqual(outcome["status"], "question")
        self.assertIn("Benfica", outcome["question"])


class UnknownReferenceTest(unittest.TestCase):
    def test_unknown_deal_asks_instead_of_guessing(self):
        move = {"deal": "No Such Deal", "payment": "part-1",
                "target_month": TARGET}
        outcome = plan_nl_move(SENTENCE, example_records(), CURRENT,
                               fake_interpret(result=move))
        self.assertEqual(outcome["status"], "question")
        self.assertIn("No Such Deal", outcome["question"])

    def test_unknown_payment_asks_instead_of_guessing(self):
        move = {"deal": "Benfica", "payment": "part-9",
                "target_month": TARGET}
        outcome = plan_nl_move(SENTENCE, example_records(), CURRENT,
                               fake_interpret(result=move))
        self.assertEqual(outcome["status"], "question")
        self.assertIn("part-9", outcome["question"])

    def test_missing_month_asks_for_month(self):
        move = {"deal": "Benfica", "payment": "part-1"}
        outcome = plan_nl_move(SENTENCE, example_records(), CURRENT,
                               fake_interpret(result=move))
        self.assertEqual(outcome["status"], "question")
        self.assertIn("month", outcome["question"].lower())

    def test_empty_sentence_asks_without_calling_model(self):
        interpret = fake_interpret(result=clear_move())
        outcome = plan_nl_move("   ", example_records(), CURRENT,
                               interpret)
        self.assertEqual(outcome["status"], "question")
        self.assertTrue(outcome["question"])
        self.assertEqual(interpret.seen, [])


class ModelFailureTest(unittest.TestCase):
    def test_model_failure_is_an_error_not_a_guess(self):
        records = example_records()
        snapshot = copy.deepcopy(records)
        interpret = fake_interpret(error=ModelError("boom"))
        outcome = plan_nl_move(SENTENCE, records, CURRENT, interpret)
        self.assertEqual(outcome["status"], "error")
        self.assertTrue(outcome["message"])
        self.assertNotIn("after", outcome)
        self.assertEqual(records, snapshot)

    def test_unreadable_answer_is_an_error(self):
        interpret = fake_interpret(result="Benfica?")
        outcome = plan_nl_move(SENTENCE, example_records(), CURRENT,
                               interpret)
        self.assertEqual(outcome["status"], "error")


class ModelClientTest(unittest.TestCase):
    def test_default_model_name(self):
        self.assertEqual(MODEL_NAME, "muse-spark-1.3")

    def test_missing_api_key_refused(self):
        with mock.patch.dict(os.environ):
            os.environ.pop(API_KEY_ENV_VAR, None)
            with self.assertRaises(ModelError):
                MetaMoveClient()

    def test_api_key_from_environment(self):
        with mock.patch.dict(os.environ, {API_KEY_ENV_VAR: "test-key"}):
            MetaMoveClient()

    def test_explicit_key_needs_no_environment(self):
        with mock.patch.dict(os.environ):
            os.environ.pop(API_KEY_ENV_VAR, None)
            MetaMoveClient(api_key="test-key")

    def test_interface_raises_until_implemented(self):
        with self.assertRaises(NotImplementedError):
            MoveModelClient().interpret_move(SENTENCE)

    def test_real_client_is_an_interpretation_client(self):
        self.assertTrue(issubclass(MetaMoveClient, MoveModelClient))


if __name__ == "__main__":
    unittest.main()
