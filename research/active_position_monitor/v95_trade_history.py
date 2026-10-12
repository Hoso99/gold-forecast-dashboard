"""Append-only, idempotent history for V9.5 hypothetical closed trades."""
import json
import os
from pathlib import Path


def trade_id(position):
    opened = position.get("opened_at")
    if not opened:
        raise ValueError("Closed trade missing opened_at")
    return "V95-" + str(opened)


def record_closed_trade(state, history_file):
    """Save the latest closed paper trade once; return True if appended."""
    position = state.get("last_closed_position")
    if not position or not position.get("exit_action"):
        return False

    path = Path(history_file)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    record = dict(position)
    identifier = trade_id(position)

    if path.exists():
        with path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                existing = json.loads(line)
                if (
                    existing.get("trade_id") == identifier
                    or (
                        existing.get("opened_at") == position.get("opened_at")
                        and existing.get("entry") == position.get("entry")
                    )
                ):
                    return False

    record["trade_id"] = identifier
    record["paper_only"] = True

    with path.open("a", encoding="utf-8") as f:
        os.chmod(path, 0o600)
        f.write(json.dumps(record, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())

    return True
