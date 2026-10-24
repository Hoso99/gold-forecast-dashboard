import unittest
from research.v96_liquidity_sweep.fibonacci import premium_zone, in_zone

class FibonacciTests(unittest.TestCase):
    def test_strict_zone(self):
        a, b = premium_zone(4000, 3900, 0.618, 0.786)
        self.assertAlmostEqual(a, 3961.8)
        self.assertAlmostEqual(b, 3978.6)

    def test_flexible_zone(self):
        self.assertTrue(in_zone(3955, 4000, 3900))
        self.assertFalse(in_zone(3955, 4000, 3900, 0.618, 0.786))

    def test_invalid_impulse(self):
        with self.assertRaises(ValueError):
            premium_zone(3900, 4000)

if __name__ == "__main__":
    unittest.main()
