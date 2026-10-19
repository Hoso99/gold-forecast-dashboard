"""V9.5 PAPER open-position stale-retry contract tests (no Oracle services)."""
import unittest
from v95_stale_retry_research import read_with_stale_retry, STALE_MARKER


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class OpenPositionProtectionTests(unittest.TestCase):
    def test_open_position_evaluated_after_refresh_only(self):
        clock = Clock()
        state = {"paper_position": {"side": "SELL", "sl": 102.0, "tp": 96.0}}
        evaluations = []
        attempts = [0]

        def read():
            attempts[0] += 1
            if attempts[0] <= 2:
                raise RuntimeError(STALE_MARKER)
            return [{"c": 103.0}]

        def evaluate(rows):
            evaluations.append((clock.now, rows[0]["c"]))
            if state["paper_position"] and rows[0]["c"] >= state["paper_position"]["sl"]:
                return "PAPER_SL_HIT"
            return "HOLD"

        rows = read_with_stale_retry(read, timeout_seconds=20, interval_seconds=2,
                                     monotonic=clock.monotonic, sleep=clock.sleep)
        self.assertEqual(evaluate(rows), "PAPER_SL_HIT")
        self.assertEqual(evaluations, [(4.0, 103.0)])

    def test_open_position_does_not_evaluate_unvalidated_data(self):
        clock = Clock()
        evaluations = []

        def read():
            raise RuntimeError(STALE_MARKER)

        with self.assertRaisesRegex(RuntimeError, STALE_MARKER):
            rows = read_with_stale_retry(read, timeout_seconds=20, interval_seconds=2,
                                         monotonic=clock.monotonic, sleep=clock.sleep)
            evaluations.append(rows)
        self.assertEqual(evaluations, [])
        self.assertEqual(clock.now, 20.0)

    def test_other_failure_does_not_delay_open_position(self):
        clock = Clock()

        def read():
            raise RuntimeError("WAIT_DATA: incomplete M1")

        with self.assertRaisesRegex(RuntimeError, "incomplete M1"):
            read_with_stale_retry(read, timeout_seconds=20, interval_seconds=2,
                                  monotonic=clock.monotonic, sleep=clock.sleep)
        self.assertEqual(clock.now, 0.0)


if __name__ == "__main__":
    unittest.main()
