"""Read-only metadata inventory for research candle archives.

Never opens, copies, or modifies a database.
"""
from pathlib import Path

ROOTS = (
    Path("/tmp/v95-85pct-history-test"),
    Path("/tmp/v95-liquidity-sweep-research"),
)

def inventory():
    records = []
    for root in ROOTS:
        for path in sorted(root.glob("*.sqlite3")):
            records.append((str(path), path.stat().st_size))
    return records

if __name__ == "__main__":
    for name, size in inventory():
        print(name, size)
