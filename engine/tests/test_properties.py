"""Structural properties of the calculation engine.

Rounding mode, monthly aggregation without re-rounding, distinct monthly
keys, refusal of float and invalid inputs, and determinism. Money is
integer cents everywhere; the float literals below are intentional probes
asserting that float input is refused, never values in the money path.
"""

import unittest

import engine
from engine import ENGINE_VERSION
from engine.calc import calc_month, calc_part


def simple_part(base, iva="0", retencao="0", irs="0", ss="0", other=None):
    """Build a monthly part dict with the given rates."""
    part = {
        "part_base": base,
        "iva_rate": iva,
        "retencao_rate": retencao,
        "irs_rate": irs,
        "ss_rate": ss,
    }
    if other is not None:
        part["other_rates"] = other
    return part


class VersionTest(unittest.TestCase):
    def test_engine_version_is_one(self):
        self.assertEqual(ENGINE_VERSION, 1)
        self.assertEqual(engine.ENGINE_VERSION, 1)


class RoundingTest(unittest.TestCase):
    def test_half_up_not_banker_rounding(self):
        # 100 * 0.025 = 2.5 cents: half-up gives 3, banker gives 2.
        result = calc_part(100, "0.025", "0", "0", "0")
        self.assertEqual(result["iva"], 3)

    def test_each_component_rounds_independently(self):
        # Both retencao and the IRS target hit exactly .5 and round up;
        # the reserve is then the difference of the rounded values.
        result = calc_part(100, "0", "0.005", "0.005", "0")
        self.assertEqual(result["retencao"], 1)
        self.assertEqual(result["irs_target"], 1)
        self.assertEqual(result["irs_reserve"], 0)
        self.assertEqual(result["bank_inflow"], 99)


class MonthlySumTest(unittest.TestCase):
    def test_components_sum_without_rerounding(self):
        # Each part rounds 100 * 0.015 = 1.5 up to 2. Summing the raw
        # 3.0 and rounding again would give 3 instead of 4.
        parts = [simple_part(100, iva="0.015"), simple_part(100, iva="0.015")]
        month = calc_month(parts)
        self.assertEqual(month["protected_breakdown"]["iva"], 4)
        self.assertEqual(month["protected_money"], 4)
        self.assertEqual(month["commission"], 200)
        self.assertEqual(month["bank_inflow"], 204)
        self.assertEqual(month["really_available"], 200)

    def test_mixed_parts_sum_componentwise(self):
        parts = [
            simple_part(200000, iva="0.23", retencao="0.11",
                        irs="0.25", ss="0"),
            simple_part(100000, other={"fundo": "0.05"}),
        ]
        month = calc_month(parts, expenses=10000)
        self.assertEqual(month["commission"], 300000)
        self.assertEqual(month["bank_inflow"], 324000)
        self.assertEqual(month["protected_money"], 79000)
        breakdown = month["protected_breakdown"]
        self.assertEqual(breakdown["iva"], 46000)
        self.assertEqual(breakdown["irs_reserve"], 28000)
        self.assertEqual(breakdown["ss_reserve"], 0)
        self.assertEqual(breakdown["other"], {"fundo": 5000})
        self.assertEqual(month["really_available"], 235000)


class MonthlyShapeTest(unittest.TestCase):
    def test_amounts_are_distinct_keys(self):
        # Commission, bank inflow and really available coincide here at
        # 100000; they must still be separate keys with their own values.
        month = calc_month([simple_part(100000)])
        self.assertEqual(
            set(month),
            {"commission", "bank_inflow", "protected_money",
             "protected_breakdown", "really_available"})
        self.assertEqual(month["commission"], 100000)
        self.assertEqual(month["bank_inflow"], 100000)
        self.assertEqual(month["protected_money"], 0)
        self.assertEqual(month["really_available"], 100000)


class RefusalTest(unittest.TestCase):
    def test_float_rate_refused(self):
        with self.assertRaises(TypeError):
            calc_part(100000, 0.23, "0", "0", "0")  # noqa: intentional float

    def test_float_money_refused(self):
        with self.assertRaises(ValueError):
            calc_part(100000.0, "0", "0", "0", "0")  # noqa: intentional float

    def test_float_expense_refused(self):
        with self.assertRaises(ValueError):
            calc_month([simple_part(100)], expenses=10.5)  # noqa: float

    def test_text_money_refused(self):
        with self.assertRaises(ValueError):
            calc_part("100", "0", "0", "0", "0")

    def test_negative_base_refused(self):
        with self.assertRaises(ValueError):
            calc_part(-1, "0", "0", "0", "0")

    def test_rate_above_one_refused(self):
        with self.assertRaises(ValueError):
            calc_part(100, "1.5", "0", "0", "0")

    def test_negative_rate_refused(self):
        with self.assertRaises(ValueError):
            calc_part(100, "0", "-0.1", "0", "0")

    def test_bad_rate_text_refused(self):
        with self.assertRaises(ValueError):
            calc_part(100, "twenty", "0", "0", "0")

    def test_bad_other_rate_refused(self):
        with self.assertRaises(ValueError):
            calc_part(100, "0", "0", "0", "0", {"fundo": "2"})

    def test_nonfinite_rates_refused(self):
        for rate in ("NaN", "sNaN", "Infinity", "-Infinity"):
            with self.subTest(rate=rate):
                with self.assertRaises(ValueError):
                    calc_part(100000, rate, "0", "0", "0")

    def test_nan_rate_via_month_refused(self):
        with self.assertRaises(ValueError):
            calc_month([{"part_base": 100000, "iva_rate": "NaN"}])

    def test_missing_part_base_refused(self):
        with self.assertRaises(ValueError):
            calc_month([{"iva_rate": "0.23"}])

    def test_negative_expenses_refused(self):
        with self.assertRaises(ValueError):
            calc_month([simple_part(100)], expenses=-1)


class DeterminismTest(unittest.TestCase):
    def test_same_inputs_same_outputs(self):
        first = calc_part(500000, "0.23", "0.25", "0.20", "0.214")
        second = calc_part(500000, "0.23", "0.25", "0.20", "0.214")
        self.assertEqual(first, second)

    def test_results_carry_no_shared_state(self):
        first = calc_part(100000, "0", "0", "0", "0", {"fundo": "0.05"})
        first["other"]["fundo"] = 0
        fresh = calc_part(100000, "0", "0", "0", "0", {"fundo": "0.05"})
        self.assertEqual(fresh["other"], {"fundo": 5000})


if __name__ == "__main__":
    unittest.main()
