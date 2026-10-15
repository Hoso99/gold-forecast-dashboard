import unittest
from datetime import datetime, timedelta, timezone
from v95_phase_c_reliability_sim import assess_minute, coverage


class PhaseCReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.minute = datetime(2026, 10, 15, 8, 42, tzinfo=timezone.utc)
        self.complete = list(range(0, 60, 5))

    def test_healthy_independent_session_accepts_complete_minute(self):
        candle = assess_minute(self.minute, self.complete)
        self.assertIsNotNone(candle)
        self.assertEqual(candle["ticks"], 12)

    def test_primary_outage_secondary_still_collects(self):
        # Primary is unavailable, but independently observed genuine secondary ticks exist.
        self.assertIsNotNone(assess_minute(self.minute, self.complete))
        result = coverage([], [self.minute.isoformat()])
        self.assertEqual(result["secondary_only"], [self.minute.isoformat()])

    def test_shared_outage_cannot_fabricate(self):
        self.assertIsNone(assess_minute(self.minute, [], secondary_connected=False))
        self.assertIsNone(assess_minute(self.minute, [], next_tick=False))

    def test_midminute_restart_must_discard_first_minute(self):
        self.assertIsNone(assess_minute(self.minute, self.complete,
                                        first_minute_after_restart=True))
        self.assertIsNone(assess_minute(self.minute, list(range(20, 60, 5))))

    def test_reconnect_after_gap_accepts_next_full_minute_only(self):
        self.assertIsNone(assess_minute(self.minute, list(range(0, 25, 5)),
                                        next_tick=False))
        next_minute = self.minute + timedelta(minutes=1)
        self.assertIsNotNone(assess_minute(next_minute, self.complete))

    def test_delayed_last_tick_rejected(self):
        self.assertIsNone(assess_minute(self.minute, list(range(0, 51, 5))))

    def test_large_intertick_gap_rejected(self):
        self.assertIsNone(assess_minute(self.minute, [0, 5, 10, 25, 30, 35, 40, 45, 50, 55]))

    def test_no_inferred_missing_minutes(self):
        p = [self.minute.isoformat()]
        s = [(self.minute + timedelta(minutes=2)).isoformat()]
        result = coverage(p, s)
        self.assertEqual(result["shared"], [])
        self.assertEqual(result["unavailable"], [])


if __name__ == "__main__":
    unittest.main()
