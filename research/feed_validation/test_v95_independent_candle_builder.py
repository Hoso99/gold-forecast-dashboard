import unittest
from datetime import datetime, timedelta, timezone
from v95_independent_candle_builder import validate_ticks

M = datetime(2026, 10, 14, 10, 23, tzinfo=timezone.utc)

class TestBuilder(unittest.TestCase):
    def test_valid(self):
        ticks = [(M + timedelta(seconds=s), 4000.0) for s in range(0, 60, 5)]
        self.assertIsNotNone(validate_ticks(M, ticks, M + timedelta(minutes=1)))

    def test_no_confirmation(self):
        ticks = [(M + timedelta(seconds=s), 4000.0) for s in range(0, 60, 5)]
        self.assertIsNone(validate_ticks(M, ticks, None))

if __name__ == '__main__':
    unittest.main()
