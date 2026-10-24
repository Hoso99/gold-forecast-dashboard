import unittest
from research.v96_liquidity_sweep.continuity import classify_transition, continuous_segments

class ContinuityTests(unittest.TestCase):
    def test_one_minute(self):
        self.assertEqual(classify_transition("2026-01-01 00:00:00","2026-01-01 00:01:00"),"CONTIGUOUS")
    def test_missing_minute(self):
        self.assertEqual(classify_transition("2026-01-01 00:00:00","2026-01-01 00:02:00"),"GAP")
    def test_duplicate(self):
        self.assertEqual(classify_transition("2026-01-01 00:00:00","2026-01-01 00:00:00"),"DUPLICATE")
    def test_out_of_order(self):
        self.assertEqual(classify_transition("2026-01-01 00:01:00","2026-01-01 00:00:00"),"OUT_OF_ORDER")
    def test_segments(self):
        rows=[{"minute_utc":f"2026-01-01 00:{minute:02d}:00"} for minute in (0,1,4,5)]
        self.assertEqual([len(x) for x in continuous_segments(rows)],[2,2])

if __name__ == "__main__":
    unittest.main()
