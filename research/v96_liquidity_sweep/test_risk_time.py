import unittest
from datetime import datetime, timezone
from research.v96_liquidity_sweep.risk_time import position_ounces, exit_deadline

class RiskTimeTests(unittest.TestCase):
    def test_risk_parity(self):
        for entry, stop in ((4000, 4008), (3994, 4008)):
            size = position_ounces(100, entry, stop, 0.4)
            self.assertAlmostEqual(size * (stop - entry + 0.4), 100)

    def test_utc_exit(self):
        t = datetime(2026, 10, 23, 17, 30, tzinfo=timezone.utc)
        self.assertEqual(exit_deadline(t), datetime(2026, 10, 23, 18, 30, tzinfo=timezone.utc))

if __name__ == "__main__":
    unittest.main()
