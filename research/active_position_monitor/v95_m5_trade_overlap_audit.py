"""Research-only audit: temporal overlap of historical SELL trades and Biquote M5 signals.

Does not infer missing Biquote candles, and does not replay M5 exits when
there is no matched data. No operational trading or paper-monitor changes.
"""
import argparse
import json
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
import pandas as pd


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trades", default="/tmp/v95_half_r_paired_audit_oct16.json")
    p.add_argument("--db", default="/home/ubuntu/v95-detector-dev/research/feed_validation/biquote_m1.sqlite3")
    p.add_argument("--output", default="/tmp/v95_m5_trade_overlap_oct16.json")
    a = p.parse_args()
    trades = json.loads(Path(a.trades).read_text())["trades"]
    with sqlite3.connect(Path(a.db).resolve().as_uri() + "?mode=ro", uri=True) as conn:
        raw = conn.execute('SELECT minute FROM candles ORDER BY minute').fetchall()
    # Source timestamps can be epoch-minute integers or ISO datetime strings.
    from research.active_position_monitor.v95_m5_history_scan import minute_epoch
    minutes = sorted({minute_epoch(row[0]) for row in raw})
    available = set(minutes)
    complete_m5 = {b for b in {t // 5 for t in minutes}
                   if all(5*b+i in available for i in range(5))}
    matched = []
    for trade in trades:
        start = int(pd.Timestamp(trade["entry_utc"]).timestamp() // 60)
        end = int(pd.Timestamp(trade["exit_utc"]).timestamp() // 60)
        # Signal bucket b is actionable at the following M1 open (5*b+5).
        eligible = [b for b in range(start // 5 - 1, end // 5 + 1)
                    if b in complete_m5 and start < 5*b+5 <= end
                    and all(b-i in complete_m5 for i in range(16))]
        matched.append({
            "entry_utc": trade["entry_utc"],
            "exit_utc": trade["exit_utc"],
            "m5_complete_history_signal_count": len(eligible),
            "first_eligible_signal_utc": (
                datetime.fromtimestamp((5*eligible[0]+5)*60, timezone.utc).isoformat()
                if eligible else None)
        })
    report = {
        "study": "Historical SELL trades versus Biquote M5 temporal coverage audit",
        "trade_count": len(trades),
        "biquote_m1_count": len(minutes),
        "biquote_start_utc": datetime.fromtimestamp(minutes[0]*60, timezone.utc).isoformat() if minutes else None,
        "biquote_end_utc": datetime.fromtimestamp(minutes[-1]*60, timezone.utc).isoformat() if minutes else None,
        "trades_with_eligible_m5_history": sum(x["m5_complete_history_signal_count"] > 0 for x in matched),
        "total_eligible_m5_windows_during_trades": sum(x["m5_complete_history_signal_count"] for x in matched),
        "matched_trades": matched,
        "limitations": [
            "Coverage only, not reversal detection or a profitability replay",
            "M5 windows need 16 consecutive complete M5 bars",
            "M5 signal becomes actionable at next M1 open",
            "Different historical feeds may have price differences",
            "No live or paper changes"
        ]
    }
    output = Path(a.output)
    if output.exists():
        p.error("Output already exists; supply another --output path")
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k:v for k,v in report.items() if k != "matched_trades"}, indent=2))
    print("Report:", output)


if __name__ == "__main__":
    main()
