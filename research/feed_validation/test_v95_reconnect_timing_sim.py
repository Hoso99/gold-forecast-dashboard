import unittest
from datetime import datetime, timedelta, timezone
from v95_reconnect_timing_sim import assess, timing_eligible

T = datetime(2026, 10, 14, 10, 23, tzinfo=timezone.utc)

class TimingTests(unittest.TestCase):
    def test_good_timing(self):
        ticks = [T + timedelta(seconds=i) for i in range(0, 61, 5)]
        self.assertTrue(timing_eligible(T, ticks))

    def test_missing_close(self):
        ticks = [T + timedelta(seconds=i) for i in range(0, 60, 5)]
        self.assertFalse(timing_eligible(T, ticks))

    def test_backup_timing(self):
        ticks = [T + timedelta(seconds=i) for i in range(0, 61, 5)]
        outage = [(T + timedelta(seconds=20), T + timedelta(seconds=40))]
        result = assess(T, ticks, ticks, outage, ())
        self.assertTrue(result['continuity_possible'])
        self.assertFalse(result['actual_candle_validated'])

if __name__ == '__main__':
    unittest.main()
