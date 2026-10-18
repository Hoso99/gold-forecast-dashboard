"""One-run read-only feasibility gate for V9.5 original vs C2 Raw across historical M1.

Never claim a winner unless C2 Raw can be faithfully replayed on identical entries.
Does not alter the frozen benchmark, source DBs, live or paper systems.
"""
import json
import hashlib
from pathlib import Path

REPORT = Path("/home/ubuntu/v95-historical-research/derived/c2_raw_vs_scenario_2025_2026_v1.json")
SOURCE = Path("research/historical/v95_m1_paper_approx.py")
NAMES = [
    "twelve_xauusd_m1.sqlite3", "twelve_xauusd_m1_2021_2022.sqlite3",
    "twelve_xauusd_m1_2022_2023.sqlite3", "twelve_xauusd_m1_2023_2024.sqlite3",
    "twelve_xauusd_m1_2024_2025.sqlite3", "twelve_xauusd_m1_2025_2026.sqlite3",
    "twelve_xauusd_m1_2026_partial.sqlite3",
]
ROOT = Path("/home/ubuntu/v95-historical-research")
OUT = Path("v95-original-vs-c2-full-history.json")

def structure(obj, depth=0):
    if depth >= 3:
        return type(obj).__name__
    if isinstance(obj, dict):
        return {str(k): structure(v, depth+1) for k,v in list(obj.items())[:35]}
    if isinstance(obj, list):
        return {"type":"list", "count":len(obj), "first_item_shape":structure(obj[0], depth+1) if obj else None}
    return type(obj).__name__

def main():
    result = {
        "research_only": True, "comparison_requested": "V9.5 original exits vs frozen C2 Raw",
        "requested_scope": "all seven historical XAU/USD M1 SQLite datasets (2020-2026)",
        "comparison_status": "NOT_YET_VALIDATED",
        "winner": None,
        "production_changes": False,
        "c2_report": str(REPORT),
        "historical_sources": [],
        "conditions": [
            "Identical entry timestamps and SELL position sizing",
            "Same stop-first protective SL/TP, spread/cost, gap and timeout policy",
            "C2 Raw algorithm and its frozen version must be available for full-history replay",
            "No fabricated historical news, partial exits, or fills",
            "Matched completed results plus censoring and per-year metrics",
        ],
    }
    for name in NAMES:
        p = ROOT/name
        result["historical_sources"].append({"name":name,"exists":p.is_file()})
    result["original_source_sha256"] = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    try:
        data = json.loads(REPORT.read_text())
        result["c2_report_available"] = True
        result["c2_report_shape"] = structure(data)
        if isinstance(data,dict):
            result["c2_top_level_keys"] = list(data)[:80]
    except (OSError, ValueError) as exc:
        result["c2_report_available"] = False
        result["c2_report_error"] = type(exc).__name__
    # A 2025-26 precomputed scenario report cannot establish all-history
    # paired performance, even when it includes six rejected episodes.
    result["comparison_status"] = "BLOCKED_FULL_HISTORY_C2_REPLAY_NOT_VERIFIED"
    result["next_required"] = (
        "Locate and pin the frozen C2 Raw detector implementation and its "
        "exact input/exit semantics, then replay on all M1 data alongside original."
    )
    OUT.write_text(json.dumps(result,indent=2)+"\n")
    print("FULL_HISTORY_PARITY_GATE",result["comparison_status"])
    print("C2_REPORT_AVAILABLE",result.get("c2_report_available"))
    print("HISTORICAL_FILES_PRESENT",sum(x["exists"] for x in result["historical_sources"]),"/",len(NAMES))
    print("NO_WINNER_DECLARED")
    print("RESEARCH_ONLY_COMPARISON_GATE_COMPLETE")

if __name__=="__main__":
    main()
