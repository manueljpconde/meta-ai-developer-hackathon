"""Item 6 C7: the expenses subtracted from one month."""
import unittest

from engine.calc import calc_month, month_expenses

NOW = "2026-11"


class MonthExpensesTest(unittest.TestCase):
    def test_a_past_month_uses_only_the_recorded_expenses(self):
        self.assertEqual(month_expenses("2026-10", NOW, 35000, recorded_cents=12000), (12000, False))
        self.assertEqual(month_expenses("2026-10", NOW, 35000), (0, False))

    def test_a_future_month_uses_the_estimate_plus_the_planned_expenses(self):
        self.assertEqual(month_expenses("2026-12", NOW, 35000), (35000, True))
        self.assertEqual(month_expenses("2027-01", NOW, 35000, recorded_cents=50000, planned_cents=20000),
                         (55000, True))

    def test_the_current_month_uses_the_larger_of_recorded_and_estimate(self):
        self.assertEqual(month_expenses(NOW, NOW, 35000, recorded_cents=10000), (35000, True))
        self.assertEqual(month_expenses(NOW, NOW, 35000, recorded_cents=40000), (40000, False))
        self.assertEqual(month_expenses(NOW, NOW, 35000, recorded_cents=35000), (35000, False))

    def test_changing_the_estimate_never_changes_a_past_month(self):
        for estimate in (0, 35000, 99900):
            self.assertEqual(month_expenses("2026-01", NOW, estimate, recorded_cents=777), (777, False))

    def test_amounts_must_be_non_negative_integer_cents(self):
        for bad in (-1, 1.5, "10", True):
            with self.assertRaises(ValueError):
                month_expenses(NOW, NOW, bad)
            with self.assertRaises(ValueError):
                month_expenses(NOW, NOW, 0, recorded_cents=bad)


class EmptyMonthTest(unittest.TestCase):
    def test_a_month_without_parts_still_carries_its_expenses(self):
        result = calc_month([], expenses=35000)
        self.assertEqual((result["commission"], result["bank_inflow"], result["protected_money"]), (0, 0, 0))
        self.assertEqual(result["really_available"], -35000)


if __name__ == "__main__":
    unittest.main()
