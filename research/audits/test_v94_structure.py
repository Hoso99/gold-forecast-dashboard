"""Structural plan regression tests, entirely offline and with synthetic candles."""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = (ROOT / "entry_watch_v94.py").read_text(encoding="utf-8")
STRUCTURE = (ROOT / "structure_risk_v94.py").read_text(encoding="utf-8")


class StructuralRiskTests(unittest.TestCase):
    def test_watcher_checks_plan_status_before_stop(self):
        tree = ast.parse(SRC)
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "calculate_current_setup")
        source = ast.get_source_segment(SRC, node)
        self.assertIn('plan.get("status") != "ACTIVE"', source)
        self.assertLess(source.index('plan.get("status")'), source.index('stop_loss = float(plan.get("stop"'))

    def test_structure_module_requires_minimum_target_rr(self):
        tree = ast.parse(STRUCTURE)
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "structure_atr_plan")
        source = ast.get_source_segment(STRUCTURE, node)
        self.assertIn("tp1_rr < min_tp1_rr", source)
        self.assertIn('"status":"ACTIVE"', source)

    def test_paper_journal_resolves_both_legacy_and_new_open_states(self):
        tree = ast.parse(SRC)
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "update_open_trades")
        source = ast.get_source_segment(SRC, node)
        self.assertIn('"OPEN", "PAPER_OPEN"', source)
        self.assertIn('"AMBIGUOUS"', source)
        self.assertIn('"WIN"', source)
        self.assertIn('"LOSS"', source)


if __name__ == "__main__":
    unittest.main()
