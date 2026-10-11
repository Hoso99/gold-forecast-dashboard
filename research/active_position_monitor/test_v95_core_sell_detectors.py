import unittest
from v95_core_sell_detectors import detect


class CoreSellDetectorTests(unittest.TestCase):
    def setUp(self):
        self.base = [
            {"o": 100, "h": 102, "l": 98, "c": 100}
            for _ in range(17)
        ]

    def test_strong_bearish_liquidity_sweep(self):
        candle = {"o": 101, "h": 105, "l": 99, "c": 100}
        result = detect(self.base + [candle], 4.0, 70.0)
        self.assertTrue(result["bearish_liquidity_sweep"])
        self.assertFalse(result["enhanced_support_break"])
        self.assertTrue(result["structural_sell"])

    def test_enhanced_support_break(self):
        candle = {"o": 99, "h": 100, "l": 95, "c": 96}
        result = detect(self.base + [candle], 4.0, 70.0)
        self.assertTrue(result["enhanced_support_break"])
        self.assertFalse(result["bearish_liquidity_sweep"])
        self.assertTrue(result["structural_sell"])

    def test_weak_sweep_rejected(self):
        candle = {"o": 103, "h": 105, "l": 99, "c": 100}
        result = detect(self.base + [candle], 4.0, 70.0)
        self.assertFalse(result["bearish_liquidity_sweep"])

    def test_insufficient_sell_pressure(self):
        candle = {"o": 101, "h": 105, "l": 99, "c": 100}
        result = detect(self.base + [candle], 4.0, 55.0)
        self.assertFalse(result["structural_sell"])

    def test_insufficient_history(self):
        result = detect(self.base[:5], 4.0, 70.0)
        self.assertEqual(result["status"], "INSUFFICIENT_DATA")

    def test_invalid_atr(self):
        result = detect(self.base + [self.base[-1]], 0.0, 70.0)
        self.assertEqual(result["status"], "INSUFFICIENT_DATA")


if __name__ == "__main__":
    unittest.main()
