import unittest
from research.v96_liquidity_sweep.support_location import normal_location, lenient_location

class SupportTests(unittest.TestCase):
    def test_normal_support_distance(self):
        self.assertTrue(normal_location(4000, 3980, 10))
        self.assertFalse(normal_location(4000, 3995, 10))

    def test_breakdown_exception(self):
        self.assertTrue(lenient_location(4000, 3995, 10, True))
        self.assertFalse(lenient_location(4000, 3995, 10, False))

    def test_no_unconditional_support_bypass(self):
        self.assertFalse(lenient_location(4000, 3999, 10, False))

if __name__ == "__main__":
    unittest.main()
