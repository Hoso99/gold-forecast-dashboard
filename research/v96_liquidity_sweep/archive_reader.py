"""Read-only historical candle streaming for isolated V9.6 research.

The seven archive files are ordered by their actual first candle, not filename.
No database writes, market orders, or changes to existing services.
"""
from pathlib import Path
import sqlite3

ARCHIVE = Path("/home/ubuntu/v95-historical-research")
PATTERN = "twelve_xauusd_m1*.sqlite3"

def archive_paths(root=ARCHIVE):
    found = []
    for path in Path(root).glob(PATTERN):
        uri = path.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            first = conn.execute("SELECT MIN(minute_utc) FROM candles").fetchone()[0]
        if first is not None:
            found.append((first, path))
    return [path for _, path in sorted(found)]

def iter_candles(root=ARCHIVE):
    """Yield chronological M1 dictionaries, raising on overlapping archives."""
    previous = None
    for path in archive_paths(root):
        uri = path.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            for ts, op, hi, lo, cl in conn.execute(
                "SELECT minute_utc, open, high, low, close "
                "FROM candles ORDER BY minute_utc"
            ):
                if previous is not None and ts <= previous:
                    raise ValueError("Overlapping or unsorted historical archives")
                previous = ts
                yield {"minute_utc": ts, "o": op, "h": hi, "l": lo, "c": cl}
