"""Run freshness unit tests AND candidate-monitor protective regression tests.

The monitor and helper modules come from this checkout, not Oracle runtime paths.
This is research-only; run in a disposable, network-isolated environment after
reviewing all helper imports and filesystem access. Never run on the live host.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
CANDIDATE = ROOT / "integration_candidate"
HELPERS = REPO / "research" / "active_position_monitor"
PROTECTIVE_RUNNER = CANDIDATE / "run_protective_regression.py"

TEST_MODULES = (
    "test_component_cycle_tracker",
    "test_component_freshness",
    "test_cycle_evidence",
    "test_cycle_freshness_contract",
    "test_diagnostic_freshness",
    "test_evaluation_stage_scenarios",
    "test_unified_freshness",
    "test_unified_record_adapter",
    "test_verified_cycle_adapter",
)

def main():
    if not (HELPERS / "v95_indicators.py").is_file():
        raise SystemExit("Missing checkout-local V9.5 helper modules")
    if not (CANDIDATE / "v95_paper_monitor.py").is_file():
        raise SystemExit("Missing candidate monitor")
    if not PROTECTIVE_RUNNER.is_file():
        raise SystemExit("Missing protective regression runner")

    with tempfile.TemporaryDirectory(prefix="v95-freshness-combined-") as temp:
        env = {
            "HOME": temp,
            "TMPDIR": temp,
            "V95_STATE_FILE": str(Path(temp) / "state.json"),
            "V95_JOURNAL_FILE": str(Path(temp) / "decisions.jsonl"),
            "V95_TRADE_HISTORY_FILE": str(Path(temp) / "trade_history.jsonl"),
            "V95_TELEGRAM_ENABLED": "0",
            "V95_NEWS_GATE_ENABLED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        # Pure tests: no monitor/helper imports.
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(ROOT))
        loader = unittest.TestLoader()
        suite = unittest.TestSuite(
            loader.loadTestsFromName(name) for name in TEST_MODULES
        )
        pure = unittest.TextTestRunner(verbosity=2).run(suite)
        if not pure.wasSuccessful():
            return 1

        # Protective tests: imports the candidate monitor and checkout-local
        # production helper modules. This is NOT an OS sandbox.
        completed = subprocess.run(
            [sys.executable, "-B", str(PROTECTIVE_RUNNER)],
            cwd=str(REPO),
            env=env,
            check=False,
        )
        return completed.returncode

if __name__ == "__main__":
    raise SystemExit(main())
