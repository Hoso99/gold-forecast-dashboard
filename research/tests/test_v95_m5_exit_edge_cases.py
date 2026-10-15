"""Additional edge-case tests for the isolated M5 research challenger."""
import unittest
from research.active_position_monitor.v95_m5_exit_challenger import assess

def bar(o, c, h, l):
    return {"o": o, "c": c, "h": h, "l": l}

def fixture(close):
    highs = [100, 103, 110, 104, 102, 101, 106, 103, 101, 100, 99, 98, 97, 96, 95]
    candles = [bar(h - 1, h - 2, h, h - 3) for h in highs]
    candles.append(bar(98, close, 109, 97))
    return candles

class ResearchEdgeCases(unittest.TestCase):
    def test_confirmed_close_and_power_generate_candidate(self):
        result = assess(fixture(107))
        self.assertEqual(result.reference_lower_high, 106)
        self.assertTrue(result.body_close_break)
        self.assertGreater(result.buy_power_5, 60)
        self.assertGreaterEqual(result.acceleration_pp, 10)
        self.assertEqual(result.action, "EXIT_CANDIDATE")

    def test_wick_break_with_rising_power_is_warning_not_exit(self):
        result = assess(fixture(104))
        self.assertFalse(result.body_close_break)
        self.assertEqual(result.action, "WARNING")

    def test_equal_close_is_not_confirmed_break(self):
        result = assess(fixture(106))
        self.assertFalse(result.body_close_break)
        self.assertNotEqual(result.action, "EXIT_CANDIDATE")

    def test_invalid_candle_is_rejected(self):
        candles = fixture(107)
        candles[-1]["l"] = 108
        with self.assertRaises(ValueError):
            assess(candles)

if __name__ == "__main__":
    unittest.main()
