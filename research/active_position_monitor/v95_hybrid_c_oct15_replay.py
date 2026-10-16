"""Read-only October 15 Hybrid C M1 research replay.

Run in an isolated checkout with:
  python3 -m research.active_position_monitor.v95_hybrid_c_oct15_replay \
    --db /home/ubuntu/v95-detector-dev/research/feed_validation/biquote_m1.sqlite3

Does not write files, send alerts, change services or fabricate fills.
"""
import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from research.active_position_monitor.v95_hybrid_c_research import HybridC

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True)
    args=p.parse_args()
    db=Path(args.db).resolve()
    if not db.is_file():
        raise SystemExit("Database not found")
    uri=db.as_uri()+"?mode=ro"
    with sqlite3.connect(uri,uri=True) as con:
        rows=con.execute("""
            SELECT minute, open, high, low, close FROM candles
            WHERE minute >= '2026-10-15T15:00:00'
              AND minute < '2026-10-15T17:55:00'
            ORDER BY minute
        """).fetchall()
    bars={}
    for t,o,h,l,c in rows:
        stamp=datetime.fromisoformat(t.replace("Z","+00:00"))
        if stamp.tzinfo is None:
            raise SystemExit("M1 timestamp missing timezone")
        stamp=stamp.astimezone(timezone.utc)
        if stamp.second or stamp.microsecond:
            raise SystemExit("Non-M1 timestamp")
        key=int(stamp.timestamp()//60)
        if key in bars:
            raise SystemExit("Duplicate M1")
        bars[key]={"o":o,"h":h,"l":l,"c":c}
    start=int(datetime(2026,10,15,15,0,tzinfo=timezone.utc).timestamp()//60)
    end=int(datetime(2026,10,15,17,55,tzinfo=timezone.utc).timestamp()//60)
    missing=[k for k in range(start,end) if k not in bars]
    if missing:
        raise SystemExit(f"INCOMPLETE_M1: {len(missing)} missing minutes; no result")
    model=HybridC()
    # Entry timestamp is not established by the October 15 summary.
    # This is a scenario study assuming SELL open by 15:00 UTC, not
    # a verified full position-level replay.
    model.open_initial(4144.57,4174.64,4084.43)
    print("SCENARIO ONLY: hypothetical position active by 15:00 UTC")
    print("No historical fill claims; signals are at completed M1 close")
    for k in range(start,end):
        result=model.on_completed_m1(bars[k])
        if k >= start+120 and result["action"] not in ("HOLD","WAIT"):
            ts=datetime.fromtimestamp((k+1)*60,timezone.utc).isoformat()
            print(ts,result)
        # Do not confirm an exit without a fill engine. Continue printing
        # raw candidate decisions to inspect whether detector ever rejects.
    print("Finished. No position closed, no re-entry executed.")

if __name__=="__main__":
    main()
