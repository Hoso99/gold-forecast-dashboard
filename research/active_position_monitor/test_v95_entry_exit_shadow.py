"""Offline deterministic tests for V9.5 shadow diagnostics."""
import unittest
from v95_entry_exit_shadow import body_sell_power, entry_diagnostics, exit_diagnostics


def bar(o, c, h=None, l=None):
    return {"o": o, "c": c, "h": max(o, c) if h is None else h,
            "l": min(o, c) if l is None else l}


class ShadowTests(unittest.TestCase):
    def test_sell_power(self):
        self.assertEqual(body_sell_power([bar(100, 99)]), 100)
        self.assertEqual(body_sell_power([bar(99, 100)]), 0)
        self.assertEqual(body_sell_power([bar(100, 100)]), 50)

    def test_acceleration_and_breakout(self):
        m1 = [bar(100, 101)] * 10 + [bar(101, 100)] * 10
        m15 = [bar(100, 100, 101, 99)] * 5 + [bar(99, 97, 100, 96)]
        result = entry_diagnostics(m1, [bar(100, 99)] * 4, m15)
        self.assertEqual(result["sell_power_acceleration_pp"], 100)
        self.assertTrue(result["m15_downside_breakout"])
        self.assertTrue(result["candidate_sell_evidence"])

    def test_high_sweep_rejection(self):
        m1 = [bar(101, 100)] * 20
        m15 = [bar(100, 100, 102, 98)] * 5 + [bar(102, 99, 104, 98)]
        result = entry_diagnostics(m1, [bar(101, 100)] * 4, m15)
        self.assertTrue(result["bearish_high_sweep_rejection"])

    def test_exit_warning_is_read_only(self):
        m1 = [bar(101, 100)] * 10 + [bar(100, 101)] * 10
        m5 = [bar(100, 100, 101, 98), bar(100, 101, 102, 99),
              bar(101, 102, 103, 100), bar(102, 103, 104, 101)]
        position = {"entry": 110, "current_stop": 115}
        result = exit_diagnostics(m1, m5, position)
        self.assertTrue(result["early_exit_warning"])
        self.assertEqual(result["action"], "REVIEW_EXIT")
        self.assertEqual(position["current_stop"], 115)

    def test_insufficient_data_wait(self):
        self.assertEqual(entry_diagnostics([], [], [])["status"], "INSUFFICIENT_DATA")
        self.assertEqual(exit_diagnostics([], [], {})["status"], "INSUFFICIENT_DATA")


if __name__ == "__main__":
    unittest.main()
