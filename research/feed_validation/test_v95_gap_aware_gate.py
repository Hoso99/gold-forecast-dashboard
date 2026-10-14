"""Offline gap-aware evaluation gate tests."""
import datetime as dt
import unittest
from v95_gap_aware_gate import check

UTC = dt.timezone.utc
BASE = dt.datetime(2026, 10, 12, 0, 0, tzinfo=UTC)


def rows(count=1200, omit=()):
    missing = set(omit)
    return [{"t": BASE + dt.timedelta(minutes=i), "o": 1.0, "h": 2.0,
             "l": 1.0, "c": 1.5} for i in range(count) if i not in missing]


def aggregate(bars, minutes):
    groups = {}
    for r in bars:
        t = r["t"]
        start = t.replace(hour=0, minute=(t.minute // minutes) * minutes) if minutes < 60 else (
            t.replace(hour=(t.hour // (minutes // 60)) * (minutes // 60), minute=0))
        groups.setdefault(start, []).append(r)
    out = []
    for start, chunk in sorted(groups.items()):
        if len(chunk) == minutes and all(
            chunk[i]["t"] == start + dt.timedelta(minutes=i) for i in range(minutes)
        ):
            out.append({"t": start})
    return out


class GateTests(unittest.TestCase):
    def verify(self, bars):
        now = bars[-1]["t"] + dt.timedelta(minutes=1, seconds=15)
        return check(bars, aggregate, now=now)

    def test_full_data(self):
        self.assertTrue(self.verify(rows())[0])

    def test_old_gap_outside_all_windows(self):
        self.assertTrue(self.verify(rows(1200, {20}))[0])

    def test_recent_m1_gap(self):
        self.assertFalse(self.verify(rows(1200, {1195}))[0])

    def test_gap_inside_h4_window(self):
        self.assertFalse(self.verify(rows(1200, {950}))[0])

    def test_gap_inside_m15_window(self):
        self.assertFalse(self.verify(rows(1200, {1100}))[0])

    def test_stale_data(self):
        bars = rows()
        self.assertFalse(check(bars, aggregate, now=bars[-1]["t"] +
                               dt.timedelta(minutes=5))[0])

    def test_older_latest_aggregate_rejected(self):
        self.assertFalse(self.verify(rows(1190))[0] if False else
                         check(rows(1190), aggregate,
                               now=BASE + dt.timedelta(minutes=1190, seconds=10))[0])


if __name__ == "__main__":
    unittest.main()
