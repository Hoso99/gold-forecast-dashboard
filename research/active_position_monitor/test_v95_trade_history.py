import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import v95_paper_monitor as m


class TradeHistoryTests(unittest.TestCase):
    def test_cycle_records_once(self):
        with tempfile.TemporaryDirectory() as d:
            history = Path(d) / "history.jsonl"
            state_file = Path(d) / "state.json"
            journal = Path(d) / "decisions.jsonl"
            trade = {
                "opened_at": "2026-10-12T04:14:00+00:00",
                "entry": 4198.42718,
                "exit_action": "EXIT_SELL_NOW",
                "paper_pnl": 188.238287955,
            }
            state = {"paper_position": None,
                     "last_closed_position": trade}
            with patch.object(m, "STATE", state_file), \
                 patch.object(m, "TRADE_HISTORY", history), \
                 patch.object(m, "JOURNAL", journal), \
                 patch.object(m, "market_session_open", return_value=False):
                m.save(state)
                m.cycle()
                m.cycle()
            self.assertEqual(len(history.read_text().splitlines()), 1)

    def test_open_market_records_once(self):
        with tempfile.TemporaryDirectory() as d:
            history = Path(d) / "history.jsonl"
            trade = {"opened_at": "2026-10-12T04:14:00+00:00",
                     "entry": 4198.42718, "exit_action": "EXIT_SELL_NOW"}
            state = {"paper_position": None, "last_closed_position": trade}
            with patch.object(m, "STATE", Path(d) / "state.json"), \
                 patch.object(m, "TRADE_HISTORY", history), \
                 patch.object(m, "JOURNAL", Path(d) / "decisions.jsonl"), \
                 patch.object(m, "market_session_open", return_value=True), \
                 patch.object(m, "candles", return_value=[]), \
                 patch.object(m, "evaluate", return_value=(state, "WAIT_DATA", "test")), \
                 patch.object(m, "send"):
                m.save(state)
                m.cycle()
                m.cycle()
            self.assertEqual(len(history.read_text().splitlines()), 1)
