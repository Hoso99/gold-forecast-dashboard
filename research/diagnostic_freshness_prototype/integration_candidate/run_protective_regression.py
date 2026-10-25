"""Restricted offline regression runner for isolated V9.5 candidate."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "integration_candidate"
HELPERS = (
    Path(__file__).resolve().parents[2]
    / "active_position_monitor"
)

TESTS = (
    "test_unacknowledged_partial_does_not_move_stop",
    "test_stale_m1_blocks_new_paper_sell",
    "test_0521_original_stale_entry_blocked",
    "test_daily_loss_above_three_percent_does_not_block",
    "test_news_gate_never_blocks_existing_stop",
    "test_detailed_telegram_entry_and_exit_messages",
)


def main():
    with tempfile.TemporaryDirectory(prefix="v95-regression-") as temp:
        # Replace inherited environment; never expose production credentials.
        os.environ.clear()
        os.environ.update({
            "HOME": temp,
            "V95_STATE_FILE": str(Path(temp) / "state.json"),
            "V95_JOURNAL_FILE": str(Path(temp) / "decisions.jsonl"),
            "V95_TRADE_HISTORY_FILE": str(
                Path(temp) / "trade_history.jsonl"
            ),
            "V95_TELEGRAM_ENABLED": "0",
            "V95_NEWS_GATE_ENABLED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        })

        sys.dont_write_bytecode = True
        sys.path.insert(0, str(ROOT))
        sys.path.insert(0, str(HELPERS))
        sys.path.insert(0, str(CANDIDATE))

        import test_v95_paper_monitor_isolated as tests

        suite = unittest.TestSuite(
            tests.PaperMonitorTests(name) for name in TESTS
        )

        result = unittest.TextTestRunner(verbosity=2).run(suite)

        print("\n===== RESTRICTED REGRESSION RESULTS =====")
        print(f"Tests run: {result.testsRun}")
        print(f"Failures: {len(result.failures)}")
        print(f"Errors: {len(result.errors)}")
        print("Production credentials inherited: NO")
        print("Telegram enabled: NO")
        print("Temporary state and journal: YES")
        print("Running V9.5 PAPER modified: NO")
        print("V9.4 LIVE modified: NO")
        print("Deployment performed: NO")

        return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
