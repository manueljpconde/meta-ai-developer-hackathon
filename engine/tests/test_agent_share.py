"""agent_share: one deal's share in integer cents, computed by the engine.

Section 3 checks: exact values with half-up rounding, and the same
input validation style as the existing engine functions.
"""

import unittest

from engine import calc


def share(*args):
    """Return engine.calc.agent_share, failing by assertion if missing."""
    func = getattr(calc, "agent_share", None)
    assert callable(func), "engine.calc.agent_share is missing"
    return func(*args)


class AgentShareValuesTest(unittest.TestCase):
    def test_half_of_a_large_base(self):
        self.assertEqual(share(1000000, "0.5"), 500000)

    def test_half_cent_rounds_half_up(self):
        self.assertEqual(share(1001, "0.5"), 501)

    def test_repeating_rate(self):
        self.assertEqual(share(100000, "0.333"), 33300)


class AgentShareRefusalTest(unittest.TestCase):
    def test_float_rate_refused(self):
        with self.assertRaises(TypeError):
            share(100000, 0.5)  # noqa: intentional float

    def test_rate_above_one_refused(self):
        with self.assertRaises(ValueError):
            share(100000, "1.5")

    def test_negative_base_refused(self):
        with self.assertRaises(ValueError):
            share(-1, "0.5")


if __name__ == "__main__":
    unittest.main()
