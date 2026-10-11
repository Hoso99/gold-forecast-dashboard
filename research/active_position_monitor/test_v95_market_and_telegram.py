"""Offline regression tests: V9.5 market closure and detailed Telegram delivery."""
import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v95_paper_monitor as monitor

UTC = dt.timezone.utc


class MarketAndTelegramTests(unittest.TestCase):
    def test_weekend_closed_and_reopen(self):
        samples = [
            ("2026-10-11T18:02:18+00:00", False),  # Sunday, NY 14:02
            ("2026-10-11T21:01:00+00:00", True),   # Sunday, NY 17:01
            ("2026-10-10T12:00:00+00:00", False),
            ("2026-10-09T20:59:00+00:00", True),   # Friday NY 16:59
            ("2026-10-09T21:00:00+00:00", False),  # Friday NY 17:00
            ("2026-01-11T21:59:00+00:00", False),  # Winter NY 16:59
            ("2026-01-11T22:01:00+00:00", True),   # Winter NY 17:01
        ]
        for timestamp, expected in samples:
            with self.subTest(timestamp=timestamp):
                self.assertEqual(monitor.market_session_open(dt.datetime.fromisoformat(timestamp)), expected)

    def test_closed_market_never_fetches_or_evaluates(self):
        state = {"last_bar": "preserved", "paper_position": {"entry": 4100},
                 "last_event": "WAIT_SELL"}
        with patch.object(monitor, "market_session_open", return_value=False), \
             patch.object(monitor, "load", return_value=state), \
             patch.object(monitor, "candles", side_effect=AssertionError("must not fetch")), \
             patch.object(monitor, "evaluate", side_effect=AssertionError("must not evaluate")), \
             patch.object(monitor, "save") as save, \
             patch.object(monitor, "journal_decision") as journal:
            self.assertEqual(monitor.cycle(), "WAIT_MARKET_CLOSED")
            self.assertEqual(state["paper_position"], {"entry": 4100})
            self.assertEqual(state["last_bar"], "preserved")
            self.assertEqual(save.call_count, 1)
            self.assertEqual(journal.call_count, 1)

    def test_alert_uses_detailed_formatter(self):
        state = {"last_event": None}
        with patch.object(monitor, "market_session_open", return_value=True), \
             patch.object(monitor, "load", return_value=state), \
             patch.object(monitor, "candles", return_value=[]), \
             patch.object(monitor, "evaluate", return_value=(state, "PAPER_SELL_ENTRY", "paper setup")), \
             patch.object(monitor, "journal_decision"), \
             patch.object(monitor, "save"), \
             patch.object(monitor, "format_alert", return_value="DETAILED ALERT") as formatter, \
             patch.object(monitor, "send") as send:
            self.assertEqual(monitor.cycle(), "PAPER_SELL_ENTRY")
            formatter.assert_called_once_with("PAPER_SELL_ENTRY", "paper setup", state)
            send.assert_called_once_with("DETAILED ALERT")


if __name__ == "__main__":
    unittest.main()
