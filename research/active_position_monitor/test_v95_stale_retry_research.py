"""Unit tests for opt-in V9.5 PAPER stale retry (no network, no state)."""
import unittest

from v95_stale_retry_research import read_with_stale_retry, STALE_MARKER


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class RetryTests(unittest.TestCase):
    def test_delayed_collector_refresh(self):
        clock = Clock()
        calls = [0]

        def read():
            calls[0] += 1
            if calls[0] < 3:
                raise RuntimeError(STALE_MARKER)
            return [{"t": "validated"}]

        self.assertEqual(
            read_with_stale_retry(read, timeout_seconds=10, interval_seconds=2,
                                  monotonic=clock.monotonic, sleep=clock.sleep),
            [{"t": "validated"}],
        )
        self.assertEqual(calls[0], 3)
        self.assertEqual(clock.now, 4)

    def test_genuine_outage_preserves_stale_failure(self):
        clock = Clock()
        calls = [0]

        def read():
            calls[0] += 1
            raise RuntimeError(STALE_MARKER)

        with self.assertRaisesRegex(RuntimeError, STALE_MARKER):
            read_with_stale_retry(read, timeout_seconds=5, interval_seconds=2,
                                  monotonic=clock.monotonic, sleep=clock.sleep)
        self.assertEqual(clock.now, 5)
        self.assertEqual(calls[0], 4)

    def test_other_data_integrity_failure_is_not_retried(self):
        clock = Clock()
        calls = [0]

        def read():
            calls[0] += 1
            raise RuntimeError("WAIT_DATA: invalid cached M1")

        with self.assertRaisesRegex(RuntimeError, "invalid cached M1"):
            read_with_stale_retry(read, monotonic=clock.monotonic, sleep=clock.sleep)
        self.assertEqual(calls[0], 1)

    def test_non_data_error_is_not_retried(self):
        clock = Clock()

        def read():
            raise PermissionError("cache unavailable")

        with self.assertRaises(PermissionError):
            read_with_stale_retry(read, monotonic=clock.monotonic, sleep=clock.sleep)
        self.assertEqual(clock.now, 0)

    def test_immediate_valid_data(self):
        clock = Clock()
        self.assertEqual(
            read_with_stale_retry(lambda: [1], monotonic=clock.monotonic,
                                  sleep=clock.sleep), [1]
        )
        self.assertEqual(clock.now, 0)

    def test_zero_timeout_does_not_wait(self):
        clock = Clock()
        with self.assertRaisesRegex(RuntimeError, STALE_MARKER):
            read_with_stale_retry(lambda: (_ for _ in ()).throw(RuntimeError(STALE_MARKER)),
                                  timeout_seconds=0, monotonic=clock.monotonic,
                                  sleep=clock.sleep)
        self.assertEqual(clock.now, 0)

    def test_invalid_configuration(self):
        with self.assertRaises(ValueError):
            read_with_stale_retry(lambda: [], interval_seconds=0)


if __name__ == "__main__":
    unittest.main()
