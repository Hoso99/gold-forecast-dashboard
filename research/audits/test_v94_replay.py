"""Offline replay tests: missing inputs must not become invented saved losses."""
import pathlib
import unittest
import importlib.util

ROOT = pathlib.Path(__file__).resolve().parents[2]
FILE = ROOT / "research/audits/replay_structure_v94.py"
spec = importlib.util.spec_from_file_location("replay_structure_v94", FILE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReplaySafetyTests(unittest.TestCase):
    def test_missing_candles_are_unknown(self):
        import pandas as pd
        candles = pd.DataFrame(columns=["open", "high", "low", "close"])
        candles.index = pd.DatetimeIndex([], tz="UTC")
        data = module.replay(candles, [{
            "side": "SELL", "model_time": "2026-10-06T12:00:00+00:00",
            "entry": 4000, "status": "LOSS", "atr_multiple": 1.5,
        }])
        self.assertEqual(data["summary"]["UNKNOWN"]["LOSS"], 1)
        self.assertEqual(data["summary"]["BLOCK"]["LOSS"], 0)

    def test_missing_adaptive_multiple_is_unknown(self):
        import pandas as pd
        ix = pd.date_range("2026-10-06", periods=70, freq="15min", tz="UTC")
        candles = pd.DataFrame({
            "open": [4000.0]*70, "high": [4005.0]*70,
            "low": [3995.0]*70, "close": [4000.0]*70,
        }, index=ix)
        data = module.replay(candles, [{
            "side": "SELL", "model_time": ix[-1].isoformat(),
            "entry": 4000, "status": "LOSS",
        }])
        self.assertEqual(data["summary"]["UNKNOWN"]["LOSS"], 1)
        self.assertEqual(data["summary"]["BLOCK"]["LOSS"], 0)


if __name__ == "__main__":
    unittest.main()
