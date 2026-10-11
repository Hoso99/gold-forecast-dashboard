"""Offline behavioral tests: execute watcher functions with mocked I/O, no secrets."""
import ast
import pathlib
import tempfile
import types
import unittest
from unittest.mock import Mock

SOURCE = (pathlib.Path(__file__).resolve().parents[2] / "entry_watch_v94.py").read_text()
TREE = ast.parse(SOURCE)


def isolated_function(name, namespace):
    node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == name)
    code = compile(ast.Module(body=[node], type_ignores=[]), "<watcher-isolated>", "exec")
    exec(code, namespace)
    return namespace[name]


class WatcherBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.ns = {
            "_secret": lambda name: "mock" if name == "TWELVE_DATA_API_KEY" else "",
            "_fresh_gold": Mock(return_value=object()),
            "update_open_trades": Mock(),
            "load_state": Mock(return_value={}),
            "save_state": Mock(),
            "append_evidence": Mock(),
            "calculate_current_setup": Mock(),
            "send_telegram_alert": Mock(return_value=types.SimpleNamespace(status="SENT", detail="mock")),
            "threshold_reached": isolated_function("threshold_reached", {}),
            "datetime": __import__("datetime").datetime,
            "timezone": __import__("datetime").timezone,
            "math": __import__("math"),
            "np": types.SimpleNamespace(nan=float("nan"), isfinite=__import__("math").isfinite),
            "MIN_RR": 2.0,
            "load_journal": Mock(return_value=[]),
            "save_journal": Mock(),
        }
        self.check = isolated_function("check_once", self.ns)
        self.setup = {
            "model_time": "2026-10-09T12:00:00+00:00",
            "side": "SELL", "basis": "mock SELL", "entry_reference": 4000.0,
            "buy_power": 0.2, "sell_power": 0.8, "threshold": 4000.0,
            "structure_reason": "mock", "stop_loss": 4010.0,
            "take_profit": 3980.0, "reward_risk": 2.0,
            "swing_high": 4008.0, "atr14": 4.0, "atr_multiple": 1.5,
            "atr_buffer": 6.0, "stop_distance": 10.0,
            "prevolatility_state": "NORMAL", "biquote_market_state": "NORMAL",
            "biquote_sell_pressure": 65.0, "biquote_velocity_change": 0.0,
            "biquote_event_risk": "NORMAL", "biquote_nearest_event": None,
            "sell_quality_status": "CONFIRMED", "sell_quality_score": 0.8,
            "sell_quality_checks_passed": 9, "sell_quality_checks_total": 9,
            "sell_candles_10": 8, "sell_candles_5": 4,
            "sell_candles_2": 2, "pressure_acceleration": 0.1,
        }
        self.ns["calculate_current_setup"].return_value = self.setup

    def test_closed_market_is_clean_skip(self):
        self.ns["_fresh_gold"].side_effect = RuntimeError(
            "Latest XAU/USD candle 2026-10-11 09:30:00+00:00 is outside the accepted market session."
        )
        self.assertIn("SKIPPED_MARKET_CLOSED", self.check())
        self.ns["send_telegram_alert"].assert_not_called()
        self.ns["append_evidence"].assert_not_called()

    def test_other_data_error_is_not_silenced(self):
        self.ns["_fresh_gold"].side_effect = RuntimeError("API timeout")
        with self.assertRaisesRegex(RuntimeError, "API timeout"):
            self.check()

    def test_wait_does_not_alert(self):
        self.setup.update(side="WAIT", threshold=None)
        self.assertIn("NO VALID THRESHOLD", self.check())
        self.ns["send_telegram_alert"].assert_not_called()

    def test_duplicate_does_not_alert(self):
        self.ns["load_state"].return_value = {
            "last_alert_key": "2026-10-09T12:00:00+00:00|SELL"
        }
        self.assertIn("ALREADY_ALERTED", self.check())
        self.ns["send_telegram_alert"].assert_not_called()

    def test_unreached_threshold_does_not_alert(self):
        self.setup["threshold"] = 4005.0
        self.assertIn("WATCHING", self.check())
        self.ns["send_telegram_alert"].assert_not_called()

    def test_new_sell_alert_is_paper_only(self):
        self.assertIn("SENT", self.check())
        self.ns["send_telegram_alert"].assert_called_once()
        rows = self.ns["save_journal"].call_args.args[0]
        self.assertEqual(rows[0]["status"], "PAPER_OPEN")
        self.assertFalse(rows[0]["execution_confirmed"])

    def test_invalid_stop_target_does_not_create_paper_trade(self):
        self.setup["stop_loss"] = 3990.0
        self.check()
        self.ns["save_journal"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
