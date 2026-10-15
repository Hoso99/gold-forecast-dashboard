"""Deterministic research tests; no API, Oracle, or production imports."""
import unittest
from research.active_position_monitor.v95_m5_exit_challenger import assess, buy_power, confirmed_lower_high

def bar(o,c,h=None,l=None):
    return {"o":o,"c":c,"h":max(o,c) if h is None else h,
            "l":min(o,c) if l is None else l}

class M5ExitTests(unittest.TestCase):
    def test_power(self):
        self.assertEqual(buy_power([bar(10,12),bar(12,11)]), 200/3)
        self.assertEqual(buy_power([bar(10,10)]), 50)
    def test_insufficient(self):
        with self.assertRaises(ValueError): assess([bar(1,2)] * 10)
    def test_wick_only_not_break(self):
        # Confirmed swing highs 110 then 106. Last candle wicks to 109,
        # but its completed close is 104: no body-close break.
        highs=[100,103,110,104,102,101,106,103,101,100,99,98,97,96,95]
        b=[bar(h-2,h-1,h,h-3) for h in highs]
        b.append(bar(98,104,109,97))
        self.assertEqual(confirmed_lower_high(b),106)
        self.assertFalse(assess(b).body_close_break)
        self.assertNotEqual(assess(b).action,"EXIT_CANDIDATE")
    def test_close_above_lower_high(self):
        highs=[100,103,110,104,102,101,106,103,101,100,99,98,97,96,95]
        b=[bar(h-2,h-1,h,h-3) for h in highs]
        b.append(bar(98,107,109,97))
        self.assertEqual(confirmed_lower_high(b),106)
        self.assertTrue(assess(b).body_close_break)
    def test_neutral_hold(self):
        self.assertEqual(assess([bar(100,100)]*16).action,"HOLD")

if __name__ == "__main__":
    unittest.main()
