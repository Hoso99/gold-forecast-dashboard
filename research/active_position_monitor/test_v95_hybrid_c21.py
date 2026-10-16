"""Synthetic C2.1 tests: causal confirmation and strict bearish reentry."""
import unittest
from research.active_position_monitor.v95_hybrid_c21 import C21Confirm, bearish_reentry_structure

def b(o,c,h=None,l=None):
    return {"o":o,"c":c,"h":max(o,c) if h is None else h,
            "l":min(o,c) if l is None else l}

class C21Tests(unittest.TestCase):
    def setUp(self):
        self.history=[b(100,100,101,99)]*5

    def test_no_timeout_only_exit(self):
        gate=C21Confirm()
        self.assertEqual(gate.observe(10,b(100,102),b(100,100),
                         "ADAPTIVE_EXIT",self.history),"WAIT")
        self.assertEqual(gate.observe(12,b(102,102),b(100,102),
                         "HOLD",self.history),"WAIT")
        self.assertEqual(gate.observe(13,b(102,102),b(102,102),
                         "HOLD",self.history),"WAIT")

    def test_followthrough_confirmation(self):
        gate=C21Confirm()
        gate.observe(10,b(100,102),b(100,100),"ADAPTIVE_EXIT",self.history)
        self.assertEqual(gate.observe(11,b(102,104),b(100,102),
                         "ADAPTIVE_EXIT",self.history),"CONFIRM")

    def test_false_reversal_cancels(self):
        gate=C21Confirm()
        gate.observe(10,b(100,102),b(100,100),"ADAPTIVE_EXIT",self.history)
        self.assertEqual(gate.observe(11,b(102,100),b(100,102),
                         "FALSE_REVERSAL_HOLD",self.history),"CANCEL")
        self.assertIsNone(gate.candidate_minute)

    def test_bearish_invalidation_cancels(self):
        gate=C21Confirm()
        gate.observe(10,b(100,102),b(100,100),"ADAPTIVE_EXIT",self.history)
        self.assertEqual(gate.observe(11,b(101,98),b(100,102,102,99),
                         "HOLD",self.history),"CANCEL")

    def test_reentry_requires_structure(self):
        self.assertFalse(bearish_reentry_structure(b(100,99.5),self.history))
        self.assertTrue(bearish_reentry_structure(b(100,98),self.history))
        self.assertFalse(bearish_reentry_structure(b(100,98),self.history[:4]))

if __name__=="__main__":
    unittest.main()
