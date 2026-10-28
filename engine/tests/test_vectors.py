"""Request vectors for the deterministic calculation engine.

Cases A to F from the request. Money is integer cents everywhere and
rates are exact decimal strings; no float appears in the money path.
"""

import unittest

from engine.calc import calc_month, calc_part


def monthly_single(base, iva="0", retencao="0", irs="0", ss="0",
                   other=None, expenses=0):
    """Run a one-part month through the monthly function."""
    part = {
        "part_base": base,
        "iva_rate": iva,
        "retencao_rate": retencao,
        "irs_rate": irs,
        "ss_rate": ss,
    }
    if other is not None:
        part["other_rates"] = other
    return calc_month([part], expenses=expenses)


class CaseATest(unittest.TestCase):
    """Retencao exceeds the IRS target, so no IRS reserve is kept."""

    def test_part_components(self):
        result = calc_part(500000, "0.23", "0.25", "0.20", "0.214")
        self.assertEqual(result["iva"], 115000)
        self.assertEqual(result["retencao"], 125000)
        self.assertEqual(result["bank_inflow"], 490000)
        self.assertEqual(result["irs_target"], 100000)
        self.assertEqual(result["irs_reserve"], 0)
        self.assertEqual(result["ss_reserve"], 107000)
        self.assertEqual(result["protected_money"], 222000)

    def test_monthly_amounts(self):
        month = monthly_single(
            500000, "0.23", "0.25", "0.20", "0.214", expenses=30000)
        self.assertEqual(month["commission"], 500000)
        self.assertEqual(month["bank_inflow"], 490000)
        self.assertEqual(month["protected_money"], 222000)
        self.assertEqual(month["really_available"], 238000)


class CaseBTest(unittest.TestCase):
    """Half-up rounding at exactly .5 (banker rounding would give 2840)."""

    def test_part_components(self):
        result = calc_part(12350, "0.23", "0", "0", "0")
        self.assertEqual(result["iva"], 2841)
        self.assertEqual(result["bank_inflow"], 15191)

    def test_monthly_amounts(self):
        month = monthly_single(12350, "0.23", "0", "0", "0")
        self.assertEqual(month["bank_inflow"], 15191)
        self.assertEqual(month["protected_money"], 2841)
        self.assertEqual(month["really_available"], 12350)


class CaseCTest(unittest.TestCase):
    """IRS target above retencao, so the difference is reserved."""

    def test_part_components(self):
        result = calc_part(200000, "0.23", "0.11", "0.25", "0")
        self.assertEqual(result["iva"], 46000)
        self.assertEqual(result["retencao"], 22000)
        self.assertEqual(result["bank_inflow"], 224000)
        self.assertEqual(result["irs_target"], 50000)
        self.assertEqual(result["irs_reserve"], 28000)
        self.assertEqual(result["ss_reserve"], 0)
        self.assertEqual(result["protected_money"], 74000)

    def test_monthly_amounts(self):
        month = monthly_single(200000, "0.23", "0.11", "0.25", "0")
        self.assertEqual(month["commission"], 200000)
        self.assertEqual(month["bank_inflow"], 224000)
        self.assertEqual(month["protected_money"], 74000)
        self.assertEqual(month["really_available"], 150000)


class CaseDTest(unittest.TestCase):
    """A named other reserve is kept and protected."""

    def test_part_components(self):
        result = calc_part(100000, "0", "0", "0", "0", {"fundo": "0.05"})
        self.assertEqual(result["other"], {"fundo": 5000})
        self.assertEqual(result["protected_money"], 5000)
        self.assertEqual(result["bank_inflow"], 100000)

    def test_monthly_amounts(self):
        month = monthly_single(
            100000, "0", "0", "0", "0", other={"fundo": "0.05"})
        self.assertEqual(month["bank_inflow"], 100000)
        self.assertEqual(month["protected_money"], 5000)
        self.assertEqual(
            month["protected_breakdown"]["other"], {"fundo": 5000})
        self.assertEqual(month["really_available"], 95000)


class CaseETest(unittest.TestCase):
    """Zero base gives zero for every component."""

    def test_part_components(self):
        result = calc_part(0, "0.23", "0.25", "0.20", "0.214")
        self.assertEqual(result["iva"], 0)
        self.assertEqual(result["retencao"], 0)
        self.assertEqual(result["bank_inflow"], 0)
        self.assertEqual(result["irs_target"], 0)
        self.assertEqual(result["irs_reserve"], 0)
        self.assertEqual(result["ss_reserve"], 0)
        self.assertEqual(result["other"], {})
        self.assertEqual(result["protected_money"], 0)

    def test_monthly_amounts(self):
        month = monthly_single(0, "0.23", "0.25", "0.20", "0.214")
        self.assertEqual(month["commission"], 0)
        self.assertEqual(month["bank_inflow"], 0)
        self.assertEqual(month["protected_money"], 0)
        self.assertEqual(month["really_available"], 0)


class CaseFTest(unittest.TestCase):
    """Really available may go negative and is never clamped."""

    def test_part_components(self):
        result = calc_part(100000, "0.23", "0", "0", "0")
        self.assertEqual(result["iva"], 23000)
        self.assertEqual(result["bank_inflow"], 123000)
        self.assertEqual(result["protected_money"], 23000)

    def test_monthly_amounts(self):
        month = monthly_single(100000, "0.23", "0", "0", "0",
                               expenses=200000)
        self.assertEqual(month["bank_inflow"], 123000)
        self.assertEqual(month["protected_money"], 23000)
        self.assertEqual(month["really_available"], -100000)


if __name__ == "__main__":
    unittest.main()
