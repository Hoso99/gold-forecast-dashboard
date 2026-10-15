import unittest
from v95_independent_signalr_adapter import decode_frames, parse_bid_tick


class AdapterTests(unittest.TestCase):
    def test_multiple_frames(self):
        self.assertEqual(len(decode_frames('{"type":1}\u001e{"type":6}\u001e')), 2)

    def test_reject_wrong_symbol(self):
        payload = {'symbol': 'EURUSD', 'time': '2026-10-15T08:00:00Z', 'bid': 4000, 'ask': 4001}
        self.assertIsNone(parse_bid_tick(payload, symbol_key='symbol', time_key='time', bid_key='bid', ask_key='ask', expected_symbol='XAUUSD'))

    def test_bid_basis(self):
        payload = {'symbol': 'XAUUSD', 'time': '2026-10-15T08:00:00Z', 'bid': 4000, 'ask': 4001}
        result = parse_bid_tick(payload, symbol_key='symbol', time_key='time', bid_key='bid', ask_key='ask', expected_symbol='XAUUSD')
        self.assertEqual(result[1], 4000)


if __name__ == '__main__':
    unittest.main()
