"""Pure unit tests; no Oracle files accessed."""
import json
import tempfile
import unittest
from pathlib import Path
from research.active_position_monitor.v95_sanitized_trade_export import sanitize, export

class ExportTests(unittest.TestCase):
    def setUp(self):
        self.trade={"opened_at":"2026-10-15T11:56:00+00:00","entry":4150.46,
                    "initial_stop":4167.28,"target":4116.82,
                    "exit_action":"TP_TOUCHED","hypothetical_fill":4116.82,
                    "paper_pnl":400.0,"telegram_token":"SECRET","api_key":"SECRET"}
    def test_allowlist(self):
        result=sanitize(self.trade)
        self.assertNotIn("telegram_token",result)
        self.assertNotIn("api_key",result)
        self.assertEqual(result["entry"],4150.46)
        self.assertNotIn("closed_at",result)
    def test_missing_required(self):
        with self.assertRaises(ValueError): sanitize({"entry":4150})
    def test_private_export_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            private=root/"private"
            private.mkdir(mode=0o700)
            source=root/"history.jsonl"
            source.write_text(json.dumps(self.trade)+"\n")
            dest=private/"export.jsonl"
            self.assertEqual(export(source,dest),1)
            result=json.loads(dest.read_text())
            self.assertNotIn("telegram_token",result)
            self.assertEqual(dest.stat().st_mode & 0o777,0o600)
            with self.assertRaises(FileExistsError): export(source,dest)
    def test_public_directory_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            public=root/"public"
            public.mkdir(mode=0o755)
            source=root/"history.jsonl"
            source.write_text(json.dumps(self.trade)+"\n")
            with self.assertRaises(PermissionError): export(source,public/"export.jsonl")

if __name__=="__main__":
    unittest.main()
