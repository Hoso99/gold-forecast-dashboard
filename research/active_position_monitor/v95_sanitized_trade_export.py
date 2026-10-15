"""Manual, allowlisted V9.5 paper-trade export for offline exit research.

NOT called by production, GitHub Actions, or any scheduled service.
Run only after confirming the V9.5 service identity and obtaining access to
its history through the existing authorized owner. No chmod/chown/sudo.
The destination must be a private directory controlled by the operator.
"""
import argparse
import json
import os
from pathlib import Path

FIELDS = (
    "trade_id", "position_id", "opened_at", "closed_at",
    "entry", "initial_stop", "target", "exit_action",
    "hypothetical_fill", "paper_pnl", "paper_units",
)
REQUIRED = ("opened_at", "entry", "initial_stop", "target", "exit_action")
NUMERIC = ("entry", "initial_stop", "target", "hypothetical_fill", "paper_pnl", "paper_units")

def sanitize(record):
    if not isinstance(record, dict):
        raise ValueError("Expected JSON object")
    if any(k not in record or record[k] is None for k in REQUIRED):
        raise ValueError("Missing required closed-trade fields")
    result = {k:record[k] for k in FIELDS if k in record and record[k] is not None}
    for k in NUMERIC:
        if k in result:
            if isinstance(result[k], bool):
                raise ValueError("Invalid numeric field")
            result[k] = float(result[k])
    # Never infer exit timestamp or fill; missing data must remain missing.
    return result

def export(input_path, output_path):
    src, dst = Path(input_path), Path(output_path)
    if src.resolve() == dst.resolve():
        raise ValueError("Input and output must differ")
    if dst.is_symlink():
        raise ValueError("Output must not be a symlink")
    if not dst.parent.is_dir():
        raise ValueError("Create the private output directory first")
    if dst.parent.stat().st_mode & 0o077:
        raise PermissionError("Output directory must be private (mode 0700)")
    rows = []
    with src.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(sanitize(json.loads(line)))
    # Exclusive creation: do not overwrite existing reports or follow symlinks.
    fd = os.open(str(dst), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True, allow_nan=False)+"\n")
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        dst.unlink(missing_ok=True)
        raise
    return len(rows)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Existing authorized V9.5 closed trade JSONL")
    parser.add_argument("--output", required=True, help="New JSONL in private 0700 directory; never overwrite")
    args = parser.parse_args()
    count = export(args.input, args.output)
    print(json.dumps({"exported_closed_paper_trades":count, "output_created":True,
                      "warning":"Contains paper trading prices; keep private. No live trading changes."}))
