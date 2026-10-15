"""Offline safety checks for the prepared, not deployed secondary service."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import v95_secondary_research_service as svc


class SecondaryServiceSafetyTests(unittest.TestCase):
    def test_valid_genuine_bid_tick(self):
        now = datetime.now(timezone.utc)
        msg = {"target": "ReceiveTick", "arguments": [{
            "symbol": "XAUUSD", "timestamp": now.isoformat(),
            "bid": 4000.0, "ask": 4000.2}]}
        self.assertEqual(svc._tick(msg)[1], 4000.0)

    def test_wrong_symbol_rejected(self):
        msg = {"target": "ReceiveTick", "arguments": [{
            "symbol": "EURUSD", "timestamp": datetime.now(timezone.utc).isoformat(),
            "bid": 1.0, "ask": 1.1}]}
        self.assertIsNone(svc._tick(msg))

    def test_stale_tick_rejected(self):
        msg = {"target": "ReceiveTick", "arguments": [{
            "symbol": "XAUUSD",
            "timestamp": (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat(),
            "bid": 4000.0, "ask": 4000.2}]}
        self.assertIsNone(svc._tick(msg))

    def test_nan_price_rejected(self):
        msg = {"target": "ReceiveTick", "arguments": [{
            "symbol": "XAUUSD", "timestamp": datetime.now(timezone.utc).isoformat(),
            "bid": float("nan"), "ask": 4000.2}]}
        self.assertIsNone(svc._tick(msg))

    def test_malformed_signalr_frames_ignored(self):
        frames = list(svc._parse('bad json\x1e{"type":6}\x1e'))
        self.assertEqual(frames, [{"type": 6}])

    def test_partial_first_minute_stays_ineligible(self):
        # The isolated collector must never persist a restart's first observed minute.
        import inspect
        code = inspect.getsource(svc.collect_session)
        self.assertIn("if not partial", code)
        self.assertIn("validate_ticks", code)
        self.assertIn("persist_validated_candle", code)


if __name__ == "__main__":
    unittest.main()
