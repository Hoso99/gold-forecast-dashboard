import csv
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from external_inputs import enrich
class ExternalInputsTests(unittest.TestCase):
    def setUp(self):
        self.d=tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
    def csv(self,name,header,rows):
        p=Path(self.d.name)/name
        with p.open("w",newline="") as f:
            w=csv.writer(f);w.writerow(header);w.writerows(rows)
        return p
    def test_asof_no_future_leak(self):
        events=self.csv("events.csv",["event_time_utc","available_at_utc","event","importance"],[
            ["2026-10-09T14:00:00Z","2026-10-09T13:30:00Z","FOMC","HIGH"],
            ["2026-10-09T14:30:00Z","2026-10-09T12:00:00Z","CPI","HIGH"]])
        macro=self.csv("macro.csv",["available_at_utc","series","value","source"],[
            ["2026-10-09T12:00:00Z","DGS10","4.5","FRED"],
            ["2026-10-09T14:00:00Z","DGS10","9.9","future"]])
        quotes=self.csv("quotes.csv",["observed_at_utc","bid","ask","source"],[
            ["2026-10-09T12:58:00Z","4000","4000.3","test"],
            ["2026-10-09T13:01:00Z","1000","1001","future"]])
        m={"07_economic_event_proximity":{"status":"UNAVAILABLE"},
           "08_spread_execution":{"status":"UNAVAILABLE"},
           "09_dxy_treasury_yields":{"status":"UNAVAILABLE"}}
        enrich(m,"2026-10-09T13:00:00+00:00",events,quotes,macro)
        self.assertEqual(m["07_economic_event_proximity"]["event"],"CPI")
        self.assertEqual(m["08_spread_execution"]["spread"],.3)
        self.assertEqual(m["09_dxy_treasury_yields"]["dgs10_pct"],4.5)
        self.assertIsNone(m["09_dxy_treasury_yields"]["dxy"])
    def test_no_inputs_remain_unavailable(self):
        m={"07_economic_event_proximity":{"status":"UNAVAILABLE"}}
        enrich(m,"2026-10-09T13:00:00Z")
        self.assertEqual(m["07_economic_event_proximity"]["status"],"UNAVAILABLE")
if __name__=="__main__":unittest.main()
