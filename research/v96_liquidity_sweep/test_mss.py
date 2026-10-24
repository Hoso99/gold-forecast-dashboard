"""Offline synthetic tests; no production services or historical databases touched."""
import unittest
from research.v96_liquidity_sweep.mss import MSSDetector, latest_confirmed_swing_low


def bar(low, high=None, close=None):
    return {"l": float(low), "h": float(high if high is not None else low + 3),
            "c": float(close if close is not None else low + 1)}


class MSSResearchTests(unittest.TestCase):
    def test_fractal_confirmation_needs_two_right_bars(self):
        b = [bar(x) for x in (101, 100, 95, 99)]
        self.assertIsNone(latest_confirmed_swing_low(b))
        b.append(bar(100))
        self.assertEqual(latest_confirmed_swing_low(b)["price"], 95)

    def test_secondary_sweep_reanchors_and_resets_clock(self):
        d = MSSDetector(max_bars=10)
        for x in (101, 100, 95, 99, 100, 98):
            d.update(bar(x))
        d.update(bar(98, 110, 102), is_sweep=True)
        self.assertEqual(d.pending.mss_level, 95)
        # New fractal low 93 is confirmed by two subsequent completed bars.
        for x in (97, 93, 96, 98):
            d.update(bar(x, high=105, close=100))
        self.assertEqual(latest_confirmed_swing_low(d.bars)["price"], 93)
        d.update(bar(100, 112, 104), is_sweep=True)
        self.assertEqual(d.pending.mss_level, 93)
        self.assertEqual(d.pending.high, 112)
        self.assertEqual(d.pending.sweep_count, 2)
        self.assertEqual(d.update(bar(92, 110, 92)), "MSS")

    def test_expiry(self):
        d = MSSDetector(max_bars=2)
        for x in (101, 100, 95, 99, 100):
            d.update(bar(x))
        d.update(bar(101, 110, 104), is_sweep=True)
        for _ in range(2):
            self.assertEqual(d.update(bar(100, 105, 100)), "WAIT")
        self.assertEqual(d.update(bar(100, 105, 100)), "EXPIRED")

    def test_new_high_without_sweep_invalidates(self):
        d = MSSDetector()
        for x in (101, 100, 95, 99, 100):
            d.update(bar(x))
        d.update(bar(100, 110, 105), is_sweep=True)
        self.assertEqual(d.update(bar(99, 111, 105)), "INVALIDATED")


if __name__ == "__main__":
    unittest.main()
