"""Run only the pure, offline freshness-classification unit tests.

This deliberately does not import v95_paper_monitor or any production helpers.
It does not execute the existing protective regression runner.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
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
    with tempfile.TemporaryDirectory(prefix="v95-freshness-pure-") as temp:
        # No inherited tokens, data feeds, or production paths.
        os.environ.clear()
        os.environ["HOME"] = temp
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(ROOT))
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        for name in TEST_MODULES:
            suite.addTests(loader.loadTestsFromName(name))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1

if __name__ == "__main__":
    raise SystemExit(main())
