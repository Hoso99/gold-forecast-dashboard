import unittest
from datetime import datetime, timedelta
from research.v96_liquidity_sweep.timeframes import aggregate_complete_m1

def make_rows(start, count):
    t=datetime.fromisoformat(start)
    return [{"minute_utc":(t+timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S"),
             "o":100+i,"h":102+i,"l":99+i,"c":101+i} for i in range(count)]

class TimeframeTests(unittest.TestCase):
    def test_complete_five(self):
        bars=list(aggregate_complete_m1(make_rows("2026-01-01 00:00:00",5),5))
        self.assertEqual(len(bars),1)
        self.assertEqual((bars[0]["o"],bars[0]["h"],bars[0]["l"],bars[0]["c"]),(100,106,99,105))
    def test_incomplete_not_emitted(self):
        self.assertEqual(list(aggregate_complete_m1(make_rows("2026-01-01 00:01:00",4),5)),[])
    def test_gap_discards_bucket(self):
        rows=make_rows("2026-01-01 00:00:00",5)
        rows.pop(2)
        self.assertEqual(list(aggregate_complete_m1(rows,5)),[])
    def test_fifteen_minute(self):
        self.assertEqual(len(list(aggregate_complete_m1(make_rows("2026-01-01 00:00:00",30),15))),2)
    def test_hourly(self):
        self.assertEqual(len(list(aggregate_complete_m1(make_rows("2026-01-01 00:00:00",60),60))),1)
    def test_four_hour(self):
        self.assertEqual(len(list(aggregate_complete_m1(make_rows("2026-01-01 00:00:00",240),240))),1)

if __name__=="__main__":
    unittest.main()
