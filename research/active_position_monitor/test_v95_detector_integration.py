"""Offline integration tests for V9.5 paper SELL detector decisions."""
import datetime as dt
import os
import unittest
from unittest.mock import patch

import v95_paper_monitor as monitor


class DetectorIntegrationTests(unittest.TestCase):
    def test_liquidity_sweep_can_trigger_without_support_break(self):
        start = dt.datetime(2026, 10, 12, 0, 0, tzinfo=dt.timezone.utc)
        rows = []

        for i in range(720):
            t = start + dt.timedelta(minutes=i)
            price = 110 - i * 0.005
            rows.append({
                "t": t,
                "o": price + 0.02,
                "h": price + 0.10,
                "l": price - 0.10,
                "c": price - 0.02,
            })

        # Create lower historical support to preserve downside room.
        for i in range(465, 480):
            rows[i]["l"] = 100.0

        # Keep previous four M15 candles above the final close.
        # Their highs establish resistance at 108.0.
        for i in range(645, 705):
            rows[i]["h"] = 108.0

        # Final completed M15 candle sweeps above resistance,
        # rejects the high, and closes above recent support.
        for i in range(705, 720):
            rows[i]["h"] = 109.0
        rows[705]["o"] = 107.0
        rows[719]["c"] = 106.4
        rows[719]["l"] = 106.3

        state = {"last_bar": None, "paper_position": None}

        with patch.dict(os.environ, {"V95_PAPER_EQUITY": "10000"}):
            result, action, note = monitor.evaluate(rows, state)

        self.assertEqual(
            action,
            "PAPER_SELL_ENTRY",
            f"Expected liquidity-sweep paper entry; got {action}: {note}",
        )
        self.assertIsNotNone(result["paper_position"])
        self.assertEqual(
            result["paper_position"]["entry_detectors"],
            ["bearish_liquidity_sweep"]
        )
        self.assertTrue(
            result["core_sell_detectors"]["bearish_liquidity_sweep"]
        )
        self.assertFalse(
            result["core_sell_detectors"]["enhanced_support_break"]
        )


if __name__ == "__main__":
    unittest.main()
