import unittest
import pandas as pd

from official_event_calendar_v830 import (
    event_risk_notice, format_events_gmt, official_event_risk)


class OfficialCalendarTests(unittest.TestCase):
    def test_event_in_next_hour_locks(self):
        now = pd.Timestamp("2026-09-24 18:00", tz="UTC")
        events = pd.DataFrame({
            "timestamp": [now + pd.Timedelta(minutes=45)],
            "source": ["BLS"], "event": ["CPI"], "impact": [3]})
        active, nearby = official_event_risk(events, now)
        self.assertTrue(active)
        self.assertEqual(len(nearby), 1)

    def test_distant_event_does_not_lock(self):
        now = pd.Timestamp("2026-09-24 18:00", tz="UTC")
        events = pd.DataFrame({
            "timestamp": [now + pd.Timedelta(hours=3)],
            "source": ["BEA"], "event": ["GDP"], "impact": [3]})
        active, nearby = official_event_risk(events, now)
        self.assertFalse(active)
        self.assertTrue(nearby.empty)

    def test_event_within_four_hours_is_elevated(self):
        now = pd.Timestamp("2026-09-24 18:00", tz="UTC")
        events = pd.DataFrame({
            "timestamp": [now + pd.Timedelta(hours=2)],
            "source": ["Fed"], "event": ["FOMC"], "impact": [3]})
        state, relevant = event_risk_notice(events, now)
        self.assertEqual(state, "ELEVATED")
        self.assertEqual(len(relevant), 1)

    def test_event_notice_formats_gmt(self):
        events = pd.DataFrame({
            "timestamp": [pd.Timestamp("2026-09-24 14:00", tz="UTC")],
            "source": ["Fed"], "event": ["FOMC"], "impact": [3]})
        shown = format_events_gmt(events)
        self.assertEqual(shown.iloc[0]["Time (GMT)"], "2026-09-24 14:00 GMT")


if __name__ == "__main__":
    unittest.main()
