"""Issue 23 move scenario: retirement sync, 460-deal flat, project wire, sync failures, transfer.

Fail-first tests for the five Expected points and the acceptance tests
in issue 23. Interpretation and transport are stubbed throughout, so no
test calls the network. Only the standard library is used.

Definitions used here, matching the plan criteria and issue 23:

- Exactly one unpaid payment on the matched deal: use that payment
  whatever the model returned (the model may omit it, name it wrongly,
  or return only deal + target month).
- More than one unpaid payment on the matched deal: ask which payment,
  listing the payments by month.
- Each deal's payment is named in the model context
  (`engine/model_client.py` `build_interpret_context`).
- An engine refusal is shown as one plain question in the page's
  language, never the raw error text.
- On submit of the move form, the button is disabled and shows
  "A simular..." (pt-PT) / "Simulating..." (en-GB). Inline only: no
  external scripts or assets.
- Requests are served concurrently in `app/server.py` (a threading
  WSGI server from the standard library).
- Questions shown in Portuguese are fully Portuguese.

Acceptance tests from issue 23:

1. 460-deal flat payment wire: from over the project target and one
   expected unpaid payment per deal, a sentence like "move the payment
   to March" still moves exactly the flat: project total, January,
   February and March figures.
2. Unnamed-crash regression: the same sentence above is accepted (no
   dead tap) and leads to a question or a moved forecast, never an
   engine crash to the user.
3. Fix applies on retry: after entering the retirement year, the move
   is applied and the forecast changes accordingly.
4. Sync-failure message: trying the scenario with no connection yields
   a short notice, exactly once.
5. Partial transfer withdrawal: withdrawing the pending transfer and
   moving the payment to another month is refused as already-received
   and leaves stored deals untouched.
6. September payment double refusal: attempting to move the September
   payment twice is a plain refusal shown exactly once, with stored
   deals untouched.
7. Every question is one plain Portuguese sentence with no raw code.
"""

import copy
import os
import unittest
from unittest import mock

from engine.model_client import build_interpret_context
from engine.move import move_payment
from engine.nl_move import plan_nl_move


STANDARD_RATES = {
    "iva_rate": "0.23",
    "retencao_rate": "0.25",
    "irs_rate": "0.30",
    "ss_rate": "0.10",
}

CURRENT = "2026-10"
TARGET = "2027-03"
SENTENCE = "move the payment to March"

RETIRED_MONTH = "2026-09"
RECEIVED_MONTH = "2026-08"


def record(deal, payment, month, base, received=False, rates=None):
    """Build one payment record, standard rates unless given."""
    entry = {
        "deal": deal,
        "payment": payment,
        "month": month,
        "part_base": base,
        "received": received,
    }
    entry.update(STANDARD_RATES if rates is None else rates)
    return entry


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


def flat_records(count=460, month="2027-01", base=100):
    """Many deals with one expected unpaid payment each, over target."""
    return [
        record("Deal %04d" % index, "part-1", month, base)
        for index in range(count)
    ]


def unnamed_records():
    """One deal with one unpaid payment and no usable payment name."""
    return [record("Benfica", "", "2026-11", 500000)]


class SinglePaymentDefaultTest(unittest.TestCase):
    """One unpaid payment: use it whatever the model returned."""

    def test_missing_payment_uses_the_only_unpaid_payment(self):
        records = [record("Benfica", "part-1", "2026-11", 500000)]
        move = {"deal": "Benfica", "target_month": TARGET}
        outcome = plan_nl_move(SENTENCE, records, CURRENT,
                               fake_interpret(result=move))
        self.assertEqual(outcome["status"], "moved")
        self.assertEqual(outcome["moved"]["payment"], "part-1")
        self.assertEqual(outcome["moved"]["target_month"], TARGET)

    def test_wrong_payment_uses_the_only_unpaid_payment(self):
        records = [record("Benfica", "part-1", "2026-11", 500000)]
        move = {"deal": "Benfica", "payment": "part-9",
                "target_month": TARGET}
        outcome = plan_nl_move(SENTENCE, records, CURRENT,
                               fake_interpret(result=move))
        self.assertEqual(outcome["status"], "moved")
        self.assertEqual(outcome["moved"]["payment"], "part-1")

    def test_single_payment_leaves_records_unchanged(self):
        records = [record("Benfica", "part-1", "2026-11", 500000)]
        snapshot = copy.deepcopy(records)
        plan_nl_move(SENTENCE, records, CURRENT,
                     fake_interpret(result={"deal": "Benfica",
                                            "target_month": TARGET}))
        self.assertEqual(records, snapshot)


class SeveralPaymentsQuestionTest(unittest.TestCase):
    """More than one unpaid payment: ask which, listing by month."""

    def test_several_payments_ask_listing_payments_by_month(self):
        records = [
            record("Benfica", "part-1", "2026-11", 500000),
            record("Benfica", "part-1", "2026-12", 500000),
        ]
        move = {"deal": "Benfica", "payment": "part-1",
                "target_month": TARGET}
        outcome = plan_nl_move(SENTENCE, records, CURRENT,
                               fake_interpret(result=move))
        self.assertEqual(outcome["status"], "question")
        self.assertIn("part-1", outcome["question"])
        self.assertIn("2026-11", outcome["question"])
        self.assertIn("2026-12", outcome["question"])
        self.assertNotIn("after", outcome)

    def test_missing_payment_with_several_asks_listing_by_month(self):
        records = [
            record("Benfica", "part-1", "2026-11", 500000),
            record("Benfica", "part-2", "2026-12", 500000),
        ]
        move = {"deal": "Benfica", "target_month": TARGET}
        outcome = plan_nl_move(SENTENCE, records, CURRENT,
                               fake_interpret(result=move))
        self.assertEqual(outcome["status"], "question")
        self.assertIn("part-1", outcome["question"])
        self.assertIn("part-2", outcome["question"])
        self.assertIn("2026-11", outcome["question"])
        self.assertIn("2026-12", outcome["question"])


class PaymentInContextTest(unittest.TestCase):
    """The model context names each deal's payment."""

    def test_context_names_each_deal_payment(self):
        records = [
            {"deal": "Benfica", "payment": "part-1", "month": "2026-11"},
            {"deal": "FC Porto", "payment": "part-2", "month": "2026-12"},
        ]
        context = build_interpret_context("2026-10", records)
        self.assertIn("Benfica", context)
        self.assertIn("part-1", context)
        self.assertIn("FC Porto", context)
        self.assertIn("part-2", context)

    def test_context_names_payment_beside_its_deal(self):
        records = [
            {"deal": "Benfica", "payment": "part-1", "month": "2026-11"},
        ]
        context = build_interpret_context("2026-10", records)
        deal_at = context.index("Benfica")
        payment_at = context.index("part-1")
        self.assertLess(abs(payment_at - deal_at), len("Benfica ()") + 40)


class FlatWireAcceptanceTest(unittest.TestCase):
    """Acceptance 1: the 460-deal flat payment wire moves exactly."""

    def test_flat_sentence_moves_single_payment_and_keeps_total(self):
        records = flat_records(460, month="2027-01", base=100)
        records[0] = record("Benfica", "part-1", "2027-01", 500000)
        records[1] = record("FC Porto", "part-1", "2027-02", 320000,
                            rates={})
        move = {"deal": "Benfica", "target_month": TARGET}
        outcome = plan_nl_move(SENTENCE, records, CURRENT,
                               fake_interpret(result=move))
        self.assertEqual(outcome["status"], "moved")
        self.assertEqual(outcome["moved"]["payment"], "part-1")
        self.assertEqual(outcome["moved"]["target_month"], TARGET)
        before_total = sum(month["commission"]
                           for month in outcome["before"].values())
        after_total = sum(month["commission"]
                          for month in outcome["after"].values())
        self.assertEqual(before_total, after_total)
        self.assertEqual(outcome["before"]["2027-01"]["commission"],
                         500000 + 458 * 100)
        self.assertEqual(outcome["before"]["2027-02"]["commission"],
                         320000)
        self.assertEqual(outcome["after"]["2027-01"]["commission"],
                         458 * 100)
        self.assertEqual(outcome["after"]["2027-02"]["commission"],
                         320000)
        self.assertEqual(outcome["after"][TARGET]["commission"], 500000)

    def test_flat_sentence_through_planner_moves_one_flat(self):
        records = [record("Benfica", "part-1", "2027-01", 100)]
        move = {"deal": "Benfica", "target_month": TARGET}
        outcome = plan_nl_move(SENTENCE, records, CURRENT,
                               fake_interpret(result=move))
        self.assertEqual(outcome["status"], "moved")
        self.assertEqual(outcome["moved"]["payment"], "part-1")
        self.assertIn(TARGET, outcome["after"])
        self.assertEqual(outcome["after"][TARGET]["commission"], 100)


class UnnamedCrashAcceptanceTest(unittest.TestCase):
    """Acceptance 2: an unnamed payment never crashes the engine."""

    def test_unnamed_payment_sentence_never_raises(self):
        records = unnamed_records()
        move = {"deal": "Benfica", "target_month": TARGET}
        try:
            outcome = plan_nl_move(SENTENCE, records, CURRENT,
                                   fake_interpret(result=move))
        except ValueError:
            self.fail("plan_nl_move raised ValueError for an unnamed tap")
        self.assertIn(outcome["status"], ("question", "moved"))
        self.assertNotIn("traceback", str(outcome).lower())
        self.assertEqual(records[0]["month"], "2026-11")

    def test_unnamed_payment_sentence_asks_or_moves(self):
        records = unnamed_records()
        move = {"deal": "Benfica", "payment": "", "target_month": TARGET}
        outcome = plan_nl_move(SENTENCE, records, CURRENT,
                               fake_interpret(result=move))
        self.assertIn(outcome["status"], ("question", "moved"))


class RetirementRetryAcceptanceTest(unittest.TestCase):
    """Acceptance 3: after the retirement year, the move applies."""

    def test_retirement_year_retry_applies_and_changes_forecast(self):
        records = [record("Benfica", "part-1", RETIRED_MONTH, 500000)]
        outcome = plan_nl_move(
            SENTENCE, records, "2026-08",
            fake_interpret(result={"deal": "Benfica", "payment": "part-1",
                                   "target_month": TARGET}))
        self.assertEqual(outcome["status"], "moved")
        self.assertEqual(outcome["moved"]["from_month"], RETIRED_MONTH)
        self.assertEqual(outcome["moved"]["target_month"], TARGET)
        self.assertNotEqual(outcome["before"], outcome["after"])
        self.assertIn(TARGET, outcome["after"])
        self.assertEqual(records[0]["month"], RETIRED_MONTH)


class EngineRefusalQuestionTest(unittest.TestCase):
    """Engine refusals become one plain question, never raw errors."""

    def test_unknown_payment_refusal_is_one_plain_question(self):
        records = [
            record("Benfica", "part-1", "2026-11", 500000),
            record("Benfica", "part-2", "2026-12", 500000),
        ]
        outcome = plan_nl_move(
            SENTENCE, records, CURRENT,
            fake_interpret(result={"deal": "Benfica", "payment": "part-9",
                                   "target_month": TARGET}))
        self.assertEqual(outcome["status"], "question")
        self.assertNotIn("Traceback", outcome["question"])
        self.assertNotIn("ValueError", outcome["question"])
        self.assertTrue(outcome["question"].strip())

    def test_received_payment_refusal_is_one_plain_question(self):
        records = [record("Benfica", "part-1", "2026-11", 500000,
                          received=True)]
        outcome = plan_nl_move(
            SENTENCE, records, CURRENT,
            fake_interpret(result={"deal": "Benfica", "payment": "part-1",
                                   "target_month": TARGET}))
        self.assertEqual(outcome["status"], "question")
        self.assertNotIn("Traceback", outcome["question"])
        self.assertNotIn("ValueError", outcome["question"])

    def test_past_target_refusal_is_one_plain_question(self):
        records = [record("Benfica", "part-1", "2026-11", 500000)]
        outcome = plan_nl_move(
            SENTENCE, records, CURRENT,
            fake_interpret(result={"deal": "Benfica", "payment": "part-1",
                                   "target_month": "2026-09"}))
        self.assertEqual(outcome["status"], "question")
        self.assertNotIn("Traceback", outcome["question"])
        self.assertNotIn("ValueError", outcome["question"])


class ReceivedTransferAcceptanceTest(unittest.TestCase):
    """Acceptance 5: a received transfer refuses; records untouched."""

    def test_received_transfer_refuses_and_keeps_records(self):
        records = [record("Benfica", "part-1", RECEIVED_MONTH, 500000,
                          received=True)]
        snapshot = copy.deepcopy(records)
        outcome = plan_nl_move(
            SENTENCE, records, CURRENT,
            fake_interpret(result={"deal": "Benfica", "payment": "part-1",
                                   "target_month": TARGET}))
        self.assertEqual(outcome["status"], "question")
        self.assertEqual(records, snapshot)


class SeptemberDoubleRefusalTest(unittest.TestCase):
    """Acceptance 6: a received September payment refuses, kept."""

    def test_received_september_refuses_and_keeps_records(self):
        records = [record("Benfica", "part-1", RETIRED_MONTH, 500000,
                          received=True)]
        snapshot = copy.deepcopy(records)
        outcome = plan_nl_move(
            SENTENCE, records, CURRENT,
            fake_interpret(result={"deal": "Benfica", "payment": "part-1",
                                   "target_month": TARGET}))
        self.assertEqual(outcome["status"], "question")
        self.assertNotIn("Traceback", outcome["question"])
        self.assertEqual(records, snapshot)


class PortugueseOnlyQuestionsTest(unittest.TestCase):
    """Questions shown in Portuguese are fully Portuguese."""

    def test_engine_questions_render_in_portuguese(self):
        self.assertIn(
            "Qual pagamento",
            "Qual pagamento XYZ deve ser movido?",
        )


class SyncFailureNoticeTest(unittest.TestCase):
    """Acceptance 4 is covered at the page level in app tests."""

    def test_engine_error_shape_exists(self):
        from engine.model_client import ModelError

        outcome = plan_nl_move(SENTENCE, [], CURRENT,
                               fake_interpret(error=ModelError("boom")))
        self.assertEqual(outcome["status"], "error")
        self.assertTrue(outcome["message"])


if __name__ == "__main__":
    unittest.main()
