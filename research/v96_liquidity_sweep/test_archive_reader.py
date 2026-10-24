import sqlite3
import tempfile
import unittest
from pathlib import Path
from research.v96_liquidity_sweep.archive_reader import archive_paths, iter_candles

class ArchiveReaderTests(unittest.TestCase):
    def test_chronological_across_files(self):
        with tempfile.TemporaryDirectory() as folder:
            for filename, timestamp in (
                ("twelve_xauusd_m1_z.sqlite3", "2020-01-01 00:00:00"),
                ("twelve_xauusd_m1_a.sqlite3", "2020-01-01 00:01:00"),
            ):
                with sqlite3.connect(str(Path(folder) / filename)) as db:
                    db.execute("CREATE TABLE candles (minute_utc TEXT, open REAL, high REAL, low REAL, close REAL)")
                    db.execute("INSERT INTO candles VALUES (?,?,?,?,?)", (timestamp, 1, 2, 1, 2))
            self.assertEqual(len(archive_paths(folder)), 2)
            rows = list(iter_candles(folder))
            self.assertEqual([x["minute_utc"] for x in rows], [
                "2020-01-01 00:00:00", "2020-01-01 00:01:00"
            ])

if __name__ == "__main__":
    unittest.main()
