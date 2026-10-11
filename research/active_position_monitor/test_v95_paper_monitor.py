"""Offline safeguards for V9.5 Oracle paper monitor."""
import datetime as dt
import importlib.util
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

P=Path(__file__).with_name("v95_paper_monitor.py")
sys.path.insert(0,str(P.parent))
spec=importlib.util.spec_from_file_location("v95_paper_monitor",P)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class PaperMonitorTests(unittest.TestCase):
    def test_aggregate_complete_only(self):
        t=dt.datetime(2026,10,12,9,0,tzinfo=dt.timezone.utc)
        rows=[{"t":t+dt.timedelta(minutes=i),"o":100.,"h":102.,
               "l":99.,"c":101.} for i in range(7)]
        self.assertEqual(len(mod.aggregate(rows,5)),1)
        self.assertEqual(mod.aggregate(rows,5)[0]["t"],t)

    def test_h4_aggregation_requires_full_aligned_240_minutes(self):
        t=dt.datetime(2026,10,12,4,0,tzinfo=dt.timezone.utc)
        rows=[{"t":t+dt.timedelta(minutes=i),"o":100.,"h":102.,
               "l":99.,"c":101.} for i in range(240)]
        self.assertEqual(len(mod.aggregate(rows,240)),1)
        self.assertEqual(mod.aggregate(rows,240)[0]["t"],t)
        self.assertEqual(len(mod.aggregate(rows[:-1],240)),0)

    def test_m5_aggregation_rejects_gaps(self):
        t=dt.datetime(2026,10,12,9,0,tzinfo=dt.timezone.utc)
        rows=[{"t":t+dt.timedelta(minutes=i),"o":100.,"h":102.,
               "l":99.,"c":101.} for i in (0,1,3,4)]
        self.assertEqual(mod.aggregate(rows,5),[])

    def test_no_signal_with_insufficient_history(self):
        state={"last_bar":None,"paper_position":None}
        got,action,note=mod.evaluate([],state)
        self.assertEqual(action,"WAIT_DATA")
        self.assertIsNone(got["paper_position"])

    def test_h4_minimum_after_twelve_hours(self):
        t=dt.datetime(2026,10,12,0,0,tzinfo=dt.timezone.utc)
        rows=[{"t":t+dt.timedelta(minutes=i),"o":100.,"h":102.,
               "l":99.,"c":101.} for i in range(720)]
        self.assertEqual(len(mod.aggregate(rows,240)),3)

    def test_unacknowledged_partial_does_not_move_stop(self):
        t=dt.datetime(2026,10,12,0,0,tzinfo=dt.timezone.utc)
        rows=[{"t":t+dt.timedelta(minutes=i),"o":100.,"h":100.1,
               "l":99.8,"c":99.9} for i in range(720)]
        state={"last_bar":None,"paper_position":{"entry":101.,"initial_stop":103.,
               "current_stop":103.,"partial_proposed":True,
               "partial_acknowledged":False,"target":97.,"opened_at":"previous"}}
        got,action,_=mod.evaluate(rows,state)
        self.assertEqual(action,"HOLD_SELL")
        self.assertEqual(got["paper_position"]["current_stop"],103.)

    def test_research_diagnostics_are_causal(self):
        from v95_indicators import ema,rsi,pressure,pivot
        self.assertIsNone(ema([1,2],3))
        self.assertEqual(ema([1,2,3],3),2)
        self.assertEqual(rsi(list(range(20))),100)
        self.assertEqual(pressure([{"o":10,"c":9}]*10),100)
        self.assertEqual(pivot({"h":12,"l":6,"c":9}),9)

    def test_biquote_calendar_includes_oil_and_cyprus_time(self):
        from v95_biquote import event_context
        now=dt.datetime(2026,10,12,12,0,tzinfo=dt.timezone.utc)
        events=[{"countryCode":"US","name":"Crude Oil Inventories",
                 "importance":"high","timeMode":"exact","time":"2026-10-12T12:30:00Z"}]
        context=event_context(events,now)
        self.assertEqual(context["risk"],"IMMINENT")
        self.assertEqual(len(context["events"]),1)
        self.assertIn("cyprus",context["events"][0])

    def test_biquote_ignores_tentative_clock(self):
        from v95_biquote import event_context
        now=dt.datetime(2026,10,12,12,0,tzinfo=dt.timezone.utc)
        events=[{"countryCode":"US","name":"FOMC","timeMode":"tentative",
                 "time":"2026-10-12T12:30:00Z"}]
        self.assertEqual(event_context(events,now)["risk"],"NORMAL")

    def test_telegram_disabled_by_default(self):
        with patch.object(mod,"ALERTS",False):
            with patch.object(mod,"urlopen") as network:
                mod.send("test")
                network.assert_not_called()

    def test_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(mod,"STATE",Path(d)/"state.json"):
                mod.save({"last_bar":"2026-10-12","paper_position":None})
                self.assertEqual(mod.load()["last_bar"],"2026-10-12")


if __name__=="__main__":
    unittest.main()
