"""Tests ensuring H4 data is advisory, while M5/M15/H1 remain mandatory."""
import datetime as dt
import unittest
from v95_gap_aware_gate import check

UTC = dt.timezone.utc
BASE = dt.datetime(2026, 10, 14, 0, 0, tzinfo=UTC)


def aggregate(rows, minutes):
    groups = {}
    for x in rows:
        start = x["t"].replace(hour=0, minute=0) + dt.timedelta(
            minutes=((x["t"].hour * 60 + x["t"].minute) // minutes) * minutes)
        groups.setdefault(start, []).append(x)
    return [{"t": start} for start, chunk in sorted(groups.items())
            if len(chunk) == minutes and
            [x["t"] for x in chunk] ==
            [start + dt.timedelta(minutes=i) for i in range(minutes)]]


class AdvisoryH4Tests(unittest.TestCase):
    def test_h4_gap_does_not_veto_valid_mandatory_windows(self):
        # Gap in old H4 bucket; most recent 5h mandatory data remains complete.
        missing = {60}
        rows = [{"t": BASE + dt.timedelta(minutes=i)}
                for i in range(120, 601) if i not in missing]
        now = BASE + dt.timedelta(minutes=601, seconds=15)
        ok, reason, detail = check(rows, aggregate, now=now)
        self.assertTrue(ok, reason)
        self.assertFalse(detail["M240"]["available"])

    def test_recent_m15_gap_still_blocks(self):
        rows = [{"t": BASE + dt.timedelta(minutes=i)}
                for i in range(120, 601) if i != 480]
        now = BASE + dt.timedelta(minutes=601, seconds=15)
        ok, reason, _ = check(rows, aggregate, now=now)
        self.assertFalse(ok)
        self.assertIn("M15", reason)


if __name__ == "__main__":
    unittest.main()
