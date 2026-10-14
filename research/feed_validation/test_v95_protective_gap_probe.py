"""Offline regression tests for research-only paper SELL protective checks."""
import datetime as dt
import unittest

from v95_protective_gap_probe import check_protective_levels

UTC = dt.timezone.utc
T = dt.datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
POS = {"entry": 100.0, "initial_stop": 105.0, "current_stop": 105.0}


def bar(minute, high=101.0, low=99.0, opening=100.0):
    return {"t": T + dt.timedelta(minutes=minute), "o": opening,
            "h": high, "l": low, "c": 100.0}


class ProtectiveGapTests(unittest.TestCase):
    def test_normal_unchanged(self):
        self.assertEqual(check_protective_levels(POS, [bar(1)], T + dt.timedelta(minutes=1))[0], "UNCHANGED")

    def test_observed_stop_takes_priority_over_target(self):
        action, detail = check_protective_levels(POS, [bar(1, high=106, low=89)])
        self.assertEqual(action, "SL_TOUCHED")
        self.assertEqual(detail["hypothetical_fill"], 105)

    def test_adverse_stop_open_is_worse_fill(self):
        action, detail = check_protective_levels(POS, [bar(1, high=110, opening=108)])
        self.assertEqual(action, "SL_TOUCHED")
        self.assertEqual(detail["hypothetical_fill"], 108)

    def test_observed_target_without_gap(self):
        self.assertEqual(check_protective_levels(POS, [bar(1, low=89)])[0], "TP_TOUCHED")

    def test_missing_prior_bar_makes_target_uncertain(self):
        action, _ = check_protective_levels(POS, [bar(3, low=89)], T)
        self.assertEqual(action, "GAP_UNCERTAIN")

    def test_missing_prior_bar_with_observed_stop(self):
        action, detail = check_protective_levels(POS, [bar(3, high=106)], T)
        self.assertEqual(action, "SL_TOUCHED")
        self.assertTrue(detail["gap_before"])

    def test_gap_without_touch_remains_uncertain(self):
        self.assertEqual(check_protective_levels(POS, [bar(1), bar(4)], T)[0], "GAP_UNCERTAIN")

    def test_multiple_contiguous_unseen_bars(self):
        self.assertEqual(check_protective_levels(POS, [bar(1), bar(2), bar(3)], T)[0],
                         "NO_PROTECTIVE_TOUCH")

    def test_bad_position_rejected(self):
        self.assertEqual(check_protective_levels(
            {"entry": 100, "initial_stop": 99, "current_stop": 105}, [bar(1)])[0],
            "WAIT_DATA")


if __name__ == "__main__":
    unittest.main()
