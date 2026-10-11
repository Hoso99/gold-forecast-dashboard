"""Offline safeguards for V9.5 Oracle paper monitor."""
import datetime as dt
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

P=Path(__file__).with_name("v95_paper_monitor.py")
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

    def test_no_signal_with_insufficient_history(self):
        state={"last_bar":None,"paper_position":None}
        got,action,note=mod.evaluate([],state)
        self.assertEqual(action,"WAIT_DATA")
        self.assertIsNone(got["paper_position"])

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
