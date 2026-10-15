"""Offline regression tests for the isolated V9.5 Biquote archive."""
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).with_name("v95_biquote_archive.py")
spec = importlib.util.spec_from_file_location("v95_biquote_archive", MODULE)
archiver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archiver)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.source = root / "primary.sqlite3"
        self.dest = root / "archive" / "candles.sqlite3"
        with sqlite3.connect(self.source) as db:
            db.execute("CREATE TABLE candles (minute TEXT PRIMARY KEY, open REAL, high REAL, low REAL, close REAL, ticks INTEGER)")
            db.execute("INSERT INTO candles VALUES (?,?,?,?,?,?)", ("2026-10-15T07:00:00+00:00", 4141, 4142, 4140, 4141.5, 25))

    def test_archives_without_modifying_primary(self):
        before = self.source.read_bytes()
        first = archiver.archive(self.source, self.dest)
        second = archiver.archive(self.source, self.dest)
        self.assertEqual((first["inserted"], second["inserted"]), (1, 0))
        self.assertEqual(before, self.source.read_bytes())
        with sqlite3.connect(self.dest) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM archived_candles").fetchone()[0], 1)

    def test_missing_source_fails_closed(self):
        with self.assertRaises(sqlite3.OperationalError):
            archiver.archive(self.source.parent / "missing.sqlite3", self.dest)
        self.assertFalse(self.dest.exists())

    def test_invalid_candle_rejected(self):
        with sqlite3.connect(self.source) as db:
            db.execute("UPDATE candles SET high=4100")
        with self.assertRaises(ValueError):
            archiver.archive(self.source, self.dest)
        self.assertFalse(self.dest.exists())

    def test_archive_conflict_not_overwritten(self):
        archiver.archive(self.source, self.dest)
        with sqlite3.connect(self.source) as db:
            db.execute("UPDATE candles SET close=4141.75")
        report = archiver.archive(self.source, self.dest)
        self.assertEqual(report["conflicts"], 1)
        with sqlite3.connect(self.dest) as db:
            self.assertEqual(db.execute("SELECT close FROM archived_candles").fetchone()[0], 4141.5)


if __name__ == "__main__":
    unittest.main()
