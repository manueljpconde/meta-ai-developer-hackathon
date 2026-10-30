"""Lenient deal matching (Q4) and bare-month resolution (Q5).

Fail-first tests for the deterministic fallbacks in
``engine.nl_move``: Unicode NFKD case- and accent-insensitive name
comparison, the next-occurrence rule for bare month names, and the
both-named question when two deals still match. Interpretation runs
through a fake, so no test calls the network.
"""

import copy
import unittest

from engine.nl_move import (
    normalize_name,
    plan_nl_move,
    resolve_month_reference,
)


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
    """Two unpaid November payments: Benfica and FC Porto."""
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


class NormalizeNameTest(unittest.TestCase):
    def test_case_insensitive(self):
        self.assertEqual(normalize_name("BENFICA"), "benfica")

    def test_accent_insensitive(self):
        self.assertEqual(normalize_name("Bénfica"), "benfica")
        self.assertEqual(normalize_name("março"), "marco")
        self.assertEqual(normalize_name("João"), "joao")

    def test_non_matching_names_stay_apart(self):
        self.assertNotEqual(normalize_name("Benfica"),
                            normalize_name("FC Porto"))


class ResolveMonthTest(unittest.TestCase):
    def test_bare_name_same_year_when_at_or_after_current(self):
        self.assertEqual(resolve_month_reference("novembro", CURRENT),
                         "2026-11")
        self.assertEqual(resolve_month_reference("outubro", CURRENT),
                         "2026-10")

    def test_bare_name_wraps_to_next_year(self):
        self.assertEqual(resolve_month_reference("janeiro", CURRENT),
                         "2027-01")

    def test_english_names_and_case_and_accents(self):
        self.assertEqual(resolve_month_reference("December", CURRENT),
                         "2026-12")
        self.assertEqual(resolve_month_reference("MARCO", "2026-10"),
                         "2027-03")

    def test_explicit_month_passes_through(self):
        self.assertEqual(resolve_month_reference("2027-01", CURRENT),
                         "2027-01")

    def test_unknown_text_resolves_to_nothing(self):
        self.assertIsNone(resolve_month_reference("someday", CURRENT))
        self.assertIsNone(resolve_month_reference("2026-13", CURRENT))
        self.assertIsNone(resolve_month_reference("", CURRENT))


class LenientMoveTest(unittest.TestCase):
    def test_lowercase_name_moves_the_registered_deal(self):
        move = {"deal": "benfica", "payment": "part-1",
                "target_month": TARGET}
        outcome = plan_nl_move(SENTENCE, example_records(), CURRENT,
                               fake_interpret(result=move))
        self.assertEqual(outcome["status"], "moved")
        self.assertEqual(outcome["moved"]["deal"], "Benfica")
        self.assertEqual(outcome["moved"]["target_month"], TARGET)

    def test_accented_name_moves_the_registered_deal(self):
        move = {"deal": "Bénfica", "payment": "part-1",
                "target_month": TARGET}
        outcome = plan_nl_move(SENTENCE, example_records(), CURRENT,
                               fake_interpret(result=move))
        self.assertEqual(outcome["status"], "moved")
        self.assertEqual(outcome["moved"]["deal"], "Benfica")

    def test_unknown_name_asks_naming_the_registered_deals(self):
        move = {"deal": "No Such Deal", "payment": "part-1",
                "target_month": TARGET}
        outcome = plan_nl_move(SENTENCE, example_records(), CURRENT,
                               fake_interpret(result=move))
        self.assertEqual(outcome["status"], "question")
        self.assertIn("No Such Deal", outcome["question"])
        self.assertIn("Benfica", outcome["question"])
        self.assertIn("FC Porto", outcome["question"])
        self.assertNotIn("after", outcome)

    def test_two_matches_ask_naming_both_with_months(self):
        records = [
            record("Benfica", "part-1", "2026-11", 500000),
            record("Bénfica", "part-1", "2026-12", 500000),
        ]
        move = {"deal": "BENFICA", "payment": "part-1",
                "target_month": TARGET}
        outcome = plan_nl_move(SENTENCE, records, CURRENT,
                               fake_interpret(result=move))
        self.assertEqual(outcome["status"], "question")
        self.assertIn("Benfica", outcome["question"])
        self.assertIn("Bénfica", outcome["question"])
        self.assertIn("2026-11", outcome["question"])
        self.assertIn("2026-12", outcome["question"])
        self.assertNotIn("after", outcome)

    def test_lenient_paths_leave_records_unchanged(self):
        records = example_records()
        snapshot = copy.deepcopy(records)
        move = {"deal": "benfica", "payment": "part-1",
                "target_month": TARGET}
        plan_nl_move(SENTENCE, records, CURRENT,
                     fake_interpret(result=move))
        self.assertEqual(records, snapshot)


class BareMonthMoveTest(unittest.TestCase):
    def test_bare_month_moves_through_the_next_occurrence_rule(self):
        move = {"deal": "Benfica", "payment": "part-1",
                "target_month": "janeiro"}
        outcome = plan_nl_move(SENTENCE, example_records(), CURRENT,
                               fake_interpret(result=move))
        self.assertEqual(outcome["status"], "moved")
        self.assertEqual(outcome["moved"]["target_month"], "2027-01")
        self.assertIn("2027-01", outcome["after"])

    def test_unknown_month_text_asks_for_the_month(self):
        move = {"deal": "Benfica", "payment": "part-1",
                "target_month": "someday"}
        outcome = plan_nl_move(SENTENCE, example_records(), CURRENT,
                               fake_interpret(result=move))
        self.assertEqual(outcome["status"], "question")
        self.assertIn("month", outcome["question"].lower())


if __name__ == "__main__":
    unittest.main()
