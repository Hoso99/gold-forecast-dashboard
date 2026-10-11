"""Research-only regression tests for the V9.4 watcher. No network or orders.

Run from repository root:
    python -m unittest discover -s research/audits -p 'test_v94_reliability.py'
"""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
WATCHER = ROOT / "entry_watch_v94.py"


class V94WatcherStaticRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WATCHER.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.functions = {
            node.name: node
            for node in cls.tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

    def test_watcher_remains_sell_only(self):
        source = ast.get_source_segment(self.source, self.functions["calculate_current_setup"])
        self.assertIn('side = "SELL"', source)
        self.assertIn('side = "WAIT"', source)

    def test_no_unconditional_threshold_reached(self):
        """Regression: hardcoded reached=True bypasses actual price trigger."""
        source = ast.get_source_segment(self.source, self.functions["check_once"])
        self.assertNotIn("reached = True", source)
        self.assertIn("threshold_reached(", source)

    def test_alert_active_is_initialized(self):
        """Regression: deduplicated alert must not reference unbound active."""
        node = self.functions["check_once"]
        first_use = next(
            x.lineno for x in ast.walk(node)
            if isinstance(x, ast.Name) and x.id == "active" and isinstance(x.ctx, ast.Load)
        )
        initializations = [
            x.lineno for x in ast.walk(node)
            if isinstance(x, ast.Name) and x.id == "active" and isinstance(x.ctx, ast.Store)
        ]
        self.assertTrue(any(line < first_use for line in initializations))
        # This static check alone cannot prove all control-flow paths; add runtime tests.

    def test_alert_is_not_recorded_as_confirmed_open_position(self):
        """Research alerts must not masquerade as broker-confirmed trades."""
        source = ast.get_source_segment(self.source, self.functions["check_once"])
        self.assertNotIn('"status": "OPEN"', source)
        self.assertIn('"record_type": "HYPOTHETICAL_SIGNAL"', source)

    def test_closed_market_has_clean_skip(self):
        source = ast.get_source_segment(self.source, self.functions["check_once"])
        self.assertIn("SKIPPED_MARKET_CLOSED", source)

    def test_duplicate_alert_returns_before_delivery(self):
        source = ast.get_source_segment(self.source, self.functions["check_once"])
        self.assertIn("ALREADY_ALERTED", source)
        self.assertLess(source.index("ALREADY_ALERTED"), source.index("send_telegram_alert("))


if __name__ == "__main__":
    unittest.main()
