"""Current month from the Lisbon date (T7) and example months (T4).

Fail-first tests: the app resolves the current month from the
server date in Europe/Lisbon with the ``APP_NL_CURRENT_MONTH``
override, and the two example deals land on the next month and the
month after, so the demo never rots into the past. No test calls
the network.
"""

import os
import unittest
from unittest import mock

from app import web


class CurrentMonthTest(unittest.TestCase):
    def test_override_wins(self):
        with mock.patch.dict(os.environ,
                             {web.NL_CURRENT_MONTH_ENV: "2030-04"}):
            self.assertEqual(web.nl_current_month(), "2030-04")

    def test_lisbon_date_without_override(self):
        import datetime

        with mock.patch.dict(os.environ):
            os.environ.pop(web.NL_CURRENT_MONTH_ENV, None)
            month = web.nl_current_month()
        self.assertRegex(month, r"^[0-9]{4}-(0[1-9]|1[0-2])$")
        today = datetime.date.today()
        this_index = today.year * 12 + today.month
        found = int(month[:4]) * 12 + int(month[5:7])
        self.assertLessEqual(abs(found - this_index), 1)

    def test_example_months_follow_the_current_month(self):
        with mock.patch.dict(os.environ,
                             {web.NL_CURRENT_MONTH_ENV: "2026-10"}):
            months = web.example_deal_months()
        self.assertEqual(months, ("2026-11", "2026-12"))

    def test_example_months_wrap_the_year(self):
        with mock.patch.dict(os.environ,
                             {web.NL_CURRENT_MONTH_ENV: "2026-12"}):
            months = web.example_deal_months()
        self.assertEqual(months, ("2027-01", "2027-02"))


if __name__ == "__main__":
    unittest.main()
