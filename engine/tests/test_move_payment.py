"""Move-payment scenario: pure forecast recalculation.

Fail-first tests for the first Cash-flow Scenario Assistant operation:
moving one selected unpaid expected payment to another month returns
the recalculated forecast without changing the given records. Refusals:
unknown deal, payment already received, past target month.
"""

import copy
import unittest

from engine.move import move_payment


STANDARD_RATES = {
    "iva_rate": "0.23",
    "retencao_rate": "0.25",
    "irs_rate": "0.30",
    "ss_rate": "0.10",
}

EXPENSES = 35000

CURRENT = "2026-10"
SOURCE = "2026-11"
TARGET = "2026-12"


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
    """Two unpaid November payments: T2 and a smaller zero-rate one."""
    return [
        record("T2 Campo de Ourique", "part-1", SOURCE, 500000),
        record("T3 Av. de Roma", "part-1", SOURCE, 320000,
               rates={}),
    ]


def example_move():
    return {
        "deal": "T2 Campo de Ourique",
        "payment": "part-1",
        "target_month": TARGET,
    }


def moved_result(records=None, move=None):
    return move_payment(
        example_records() if records is None else records,
        example_move() if move is None else move,
        CURRENT,
        expenses_cents=EXPENSES,
    )


class RecalculationTest(unittest.TestCase):
    def test_move_returns_recalculated_forecast(self):
        result = moved_result()
        self.assertEqual(sorted(result["forecast"]), [SOURCE, TARGET])
        november = result["forecast"][SOURCE]
        self.assertEqual(november["commission"], 320000)
        self.assertEqual(november["bank_inflow"], 320000)
        self.assertEqual(november["protected_money"], 0)
        self.assertEqual(november["really_available"], 285000)
        december = result["forecast"][TARGET]
        self.assertEqual(december["commission"], 500000)
        self.assertEqual(december["bank_inflow"], 490000)
        self.assertEqual(december["protected_money"], 190000)
        self.assertEqual(december["really_available"], 265000)

    def test_moved_detail_names_source_and_target(self):
        result = moved_result()
        self.assertEqual(
            result["moved"],
            {
                "deal": "T2 Campo de Ourique",
                "payment": "part-1",
                "from_month": SOURCE,
                "target_month": TARGET,
            },
        )

    def test_move_carries_named_other_reserve(self):
        records = [
            record("Quinta", "part-1", SOURCE, 100000,
                   rates={"other_rates": {"fundo": "0.05"}}),
        ]
        result = move_payment(
            records, {"deal": "Quinta", "payment": "part-1",
                      "target_month": TARGET},
            CURRENT,
        )
        december = result["forecast"][TARGET]
        self.assertEqual(december["protected_money"], 5000)
        self.assertEqual(
            december["protected_breakdown"]["other"], {"fundo": 5000})

    def test_minimal_record_defaults_to_zero_rates(self):
        records = [
            {"deal": "Solo", "payment": "part-1", "month": SOURCE,
             "part_base": 100000},
        ]
        result = move_payment(
            records, {"deal": "Solo", "payment": "part-1",
                      "target_month": TARGET},
            CURRENT,
        )
        self.assertEqual(result["forecast"][TARGET]["bank_inflow"], 100000)
        self.assertEqual(result["forecast"][TARGET]["protected_money"], 0)

    def test_received_payment_excluded_from_forecast(self):
        records = [
            record("T2 Campo de Ourique", "part-1", SOURCE, 500000,
                   received=True),
            record("T3 Av. de Roma", "part-1", SOURCE, 320000, rates={}),
        ]
        move = {"deal": "T3 Av. de Roma", "payment": "part-1",
                "target_month": TARGET}
        result = move_payment(records, move, CURRENT,
                              expenses_cents=EXPENSES)
        self.assertNotIn(SOURCE, result["forecast"])
        december = result["forecast"][TARGET]
        self.assertEqual(december["commission"], 320000)
        self.assertEqual(december["bank_inflow"], 320000)
        self.assertEqual(december["protected_money"], 0)
        self.assertEqual(december["really_available"], 285000)


class PurityTest(unittest.TestCase):
    def test_input_records_unchanged(self):
        records = example_records()
        snapshot = copy.deepcopy(records)
        moved_result(records=records)
        self.assertEqual(records, snapshot)

    def test_same_inputs_same_outputs(self):
        first = moved_result()
        second = moved_result()
        self.assertEqual(first, second)

    def test_result_shares_no_state_with_input(self):
        records = example_records()
        result = moved_result(records=records)
        result["forecast"][TARGET]["commission"] = 0
        result["moved"]["deal"] = "changed"
        self.assertEqual(records[0]["month"], SOURCE)
        fresh = moved_result()
        self.assertEqual(fresh["forecast"][TARGET]["commission"], 500000)


class RefusalTest(unittest.TestCase):
    def test_unknown_deal_refused(self):
        move = {"deal": "No Such Deal", "payment": "part-1",
                "target_month": TARGET}
        with self.assertRaises(ValueError) as ctx:
            moved_result(move=move)
        self.assertIn("No Such Deal", str(ctx.exception))

    def test_empty_records_refuse_as_unknown_deal(self):
        move = example_move()
        with self.assertRaises(ValueError):
            move_payment([], move, CURRENT)

    def test_unknown_payment_refused(self):
        move = {"deal": "T2 Campo de Ourique", "payment": "part-9",
                "target_month": TARGET}
        with self.assertRaises(ValueError) as ctx:
            moved_result(move=move)
        self.assertIn("part-9", str(ctx.exception))

    def test_received_payment_refused(self):
        records = [
            record("T2 Campo de Ourique", "part-1", SOURCE, 500000,
                   received=True),
        ]
        with self.assertRaises(ValueError) as ctx:
            moved_result(records=records)
        self.assertIn("received", str(ctx.exception))

    def test_past_target_month_refused(self):
        move = {"deal": "T2 Campo de Ourique", "payment": "part-1",
                "target_month": "2026-09"}
        with self.assertRaises(ValueError) as ctx:
            moved_result(move=move)
        self.assertIn("2026-09", str(ctx.exception))

    def test_ambiguous_duplicate_refused(self):
        records = example_records()
        records.append(record("T2 Campo de Ourique", "part-1", SOURCE,
                              500000))
        with self.assertRaises(ValueError) as ctx:
            moved_result(records=records)
        self.assertIn("ambiguous", str(ctx.exception))

    def test_bad_target_month_refused(self):
        move = {"deal": "T2 Campo de Ourique", "payment": "part-1",
                "target_month": "December"}
        with self.assertRaises(ValueError):
            moved_result(move=move)

    def test_bad_current_month_refused(self):
        with self.assertRaises(ValueError):
            move_payment(example_records(), example_move(), "soon")

    def test_move_missing_key_refused(self):
        move = {"deal": "T2 Campo de Ourique", "payment": "part-1"}
        with self.assertRaises(ValueError):
            moved_result(move=move)

    def test_bad_record_month_refused(self):
        records = [
            record("T2 Campo de Ourique", "part-1", "novembro", 500000),
        ]
        with self.assertRaises(ValueError):
            moved_result(records=records)


class BoundaryTest(unittest.TestCase):
    def test_current_month_target_allowed(self):
        move = {"deal": "T2 Campo de Ourique", "payment": "part-1",
                "target_month": CURRENT}
        result = moved_result(move=move)
        self.assertIn(CURRENT, result["forecast"])
        self.assertEqual(
            result["forecast"][CURRENT]["commission"], 500000)

    def test_same_month_move_returns_same_forecast(self):
        move = {"deal": "T2 Campo de Ourique", "payment": "part-1",
                "target_month": SOURCE}
        result = moved_result(move=move)
        november = result["forecast"][SOURCE]
        self.assertEqual(november["commission"], 820000)
        self.assertEqual(november["bank_inflow"], 810000)
        self.assertEqual(november["protected_money"], 190000)
        self.assertEqual(november["really_available"], 585000)
        self.assertNotIn(TARGET, result["forecast"])


if __name__ == "__main__":
    unittest.main()
