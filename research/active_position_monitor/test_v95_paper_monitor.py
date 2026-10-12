"""Offline safeguards for V9.5 Oracle paper monitor."""
import datetime as dt
import os
from contextlib import ExitStack
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

    def _candidate_evaluation(self,news_context,existing_position=None,detector=True):
        """Synthetic completed-bar candidate; no network or broker interaction."""
        t=dt.datetime(2026,10,12,0,0,tzinfo=dt.timezone.utc)
        rows=[{"t":t+dt.timedelta(minutes=i),"o":91.,"h":92.,
               "l":89.,"c":90.} for i in range(720)]
        m15=[{"h":100.,"l":80.,"c":95.} for _ in range(18)]
        m5=[{"c":float(100-i)} for i in range(6)]
        h1=[{"c":100.},{"c":99.},{"c":98.}]
        h4=[{"c":100.},{"c":99.}]
        state={"last_bar":None,"paper_position":existing_position,
               "realized_paper_loss":0.,"loss_day_utc":"2026-10-12"}
        bars={5:m5,15:m15,60:h1,240:h4}
        with ExitStack() as stack:
            stack.enter_context(patch.object(mod,"aggregate",side_effect=lambda _r,n:bars[n]))
            stack.enter_context(patch.object(mod,"atr",return_value=1.))
            stack.enter_context(patch.object(mod,"diagnostics",return_value={}))
            stack.enter_context(patch.object(mod,"votes",return_value={}))
            stack.enter_context(patch.object(mod,"entry_diagnostics",return_value={}))
            stack.enter_context(patch.object(mod,"exit_diagnostics",return_value={}))
            stack.enter_context(patch.object(mod,"detect_core_sell",return_value={
                "structural_sell":detector,"enhanced_support_break":detector}))
            stack.enter_context(patch.dict(os.environ,{
                "V95_PAPER_EQUITY":"10000","V95_NEWS_GATE_ENABLED":"1"}))
            return mod.evaluate(rows,state,news_context)

    def test_news_gate_blocks_imminent_new_sell(self):
        state,action,note=self._candidate_evaluation({
            "risk":"IMMINENT","events":[{"name":"CPI","minutes_to_event":12}]})
        self.assertEqual(action,"NEWS_BLOCKED")
        self.assertIn("CPI",note)
        self.assertIsNone(state["paper_position"])

    def test_news_gate_fails_closed_on_unknown(self):
        state,action,_=self._candidate_evaluation({"risk":"UNKNOWN"})
        self.assertEqual(action,"NEWS_BLOCKED")
        self.assertIsNone(state["paper_position"])

    def test_news_gate_allows_verified_normal_candidate(self):
        state,action,_=self._candidate_evaluation({"risk":"NORMAL","events":[]})
        self.assertEqual(action,"PAPER_SELL_ENTRY")
        self.assertEqual(state["paper_position"]["target"],67.)

    def test_news_gate_does_not_change_wait_sell(self):
        state,action,_=self._candidate_evaluation({"risk":"UNKNOWN"},detector=False)
        self.assertEqual(action,"WAIT_SELL")
        self.assertIsNone(state["paper_position"])

    def test_news_gate_never_blocks_existing_stop(self):
        pos={"entry":101.,"initial_stop":103.,"current_stop":91.,
             "target":97.,"paper_units":1.,"partial_proposed":False,
             "partial_acknowledged":False}
        state,action,_=self._candidate_evaluation({"risk":"UNKNOWN"},existing_position=pos)
        self.assertEqual(action,"SL_TOUCHED")
        self.assertIsNone(state["paper_position"])

    def test_calendar_fetch_does_not_require_quote(self):
        from v95_biquote import fetch_calendar_context
        now=dt.datetime(2026,10,12,12,0,tzinfo=dt.timezone.utc)
        events=[{"countryCode":"US","name":"CPI","timeMode":"exact",
                 "time":"2026-10-12T12:10:00Z"}]
        with patch("v95_biquote.get_json",return_value=events) as get_json:
            self.assertEqual(fetch_calendar_context(now)["risk"],"IMMINENT")
            self.assertEqual(get_json.call_count,1)
            self.assertIn("/api/calendar?",get_json.call_args.args[0])

    def test_news_window_boundaries(self):
        from v95_biquote import event_context
        now=dt.datetime(2026,10,12,12,0,tzinfo=dt.timezone.utc)
        for offset,expected in [(30,"IMMINENT"),(-15,"IMMINENT"),
                                (31,"BUILDING"),(-16,"NORMAL")]:
            event={"countryCode":"US","name":"FOMC","timeMode":"exact",
                   "time":(now+dt.timedelta(minutes=offset)).isoformat()}
            self.assertEqual(event_context([event],now)["risk"],expected)

    def test_four_research_votes_are_not_claimed_independent(self):
        from v95_research_votes import votes
        t=dt.datetime(2026,10,12,0,0,tzinfo=dt.timezone.utc)
        rows=[{"t":t+dt.timedelta(minutes=i),"o":100+i*0.01,
               "h":101+i*0.01,"l":99+i*0.01,"c":100+i*0.01} for i in range(30)]
        got=votes(rows,rows,rows,rows,rows)
        self.assertEqual(len(got["votes"]),4)
        self.assertFalse(got["independence_verified"])
        self.assertEqual(got["agreement"],0)

    def test_detailed_telegram_entry_and_exit_messages(self):
        from v95_telegram_format import format_alert
        pos={"entry":4200.,"initial_stop":4210.,"current_stop":4210.,
             "target":4180.,"risk_budget":200.}
        state={"paper_position":pos,"diagnostics":{"m1_sell_pressure_10":71.},
               "research_votes":{"agreement":3},
               "biquote_context":{"risk":"BUILDING"}}
        entry=format_alert("PAPER_SELL_ENTRY","research",state)
        self.assertIn("Entry: 4200.00 | SL: 4210.00 | TP: 4180.00",entry)
        self.assertIn("Target R:R: 1:2.00",entry)
        self.assertIn("NO LIVE TRADE",entry)
        state["last_closed_position"]=pos
        state["paper_position"]=None
        exit_message=format_alert("TP_TOUCHED","paper exit",state)
        self.assertIn("TAKE PROFIT TOUCHED",exit_message)
        self.assertIn("4180.00",exit_message)

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
