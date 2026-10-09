import csv
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from evaluate import bars_from_csv, calculate, power

UTC=dt.timezone.utc
class TenMeasurementsTests(unittest.TestCase):
    def setUp(self):
        t=dt.datetime(2026,10,9,9,0,tzinfo=UTC)
        self.rows=[]
        for i in range(300):
            o=4000-i*.1
            self.rows.append((t+dt.timedelta(minutes=i),o,o+.2,o-.3,o-.1))
    def test_all_ten_and_unavailable_sources(self):
        result=calculate(self.rows)
        m=result["measurements"]
        self.assertEqual(len(m),10)
        for k in ("07_economic_event_proximity","08_spread_execution","09_dxy_treasury_yields"):
            self.assertEqual(m[k]["status"],"UNAVAILABLE")
        self.assertIsNone(m["10_active_trade_deterioration"]["early_exit_signal"])
        self.assertEqual(m["05_higher_timeframe_alignment"]["h1"],"DOWN")
    def test_no_future_or_missing_m1(self):
        bad=self.rows[:]
        bad[-2]=(bad[-2][0]-dt.timedelta(seconds=30),*bad[-2][1:])
        with self.assertRaisesRegex(ValueError,"gaps"):
            calculate(bad)
    def test_pressure_range(self):
        self.assertTrue(0<=power(self.rows[-10:])<=100)
    def test_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"test.csv"
            with p.open("w",newline="") as f:
                w=csv.writer(f);w.writerow(("datetime","open","high","low","close"))
                for row in self.rows[:2]+self.rows[:1]:
                    w.writerow((row[0].isoformat(),*row[1:]))
            with self.assertRaisesRegex(ValueError,"Duplicate"):
                bars_from_csv(p)
if __name__=="__main__":
    unittest.main()
