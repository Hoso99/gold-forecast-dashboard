"""Read-only inventory of Oracle V9.5 Hybrid research outputs.

Metadata and selected aggregate keys only; never prints secrets or file contents.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

ROOTS = ["/home/ubuntu/v95-detector-dev", "/home/ubuntu/v95-private-export",
         "/tmp/v95-hybrid-c-oct15", "/tmp"]
TERMS = ("v95", "hybrid", "c2", "reversal", "exit", "episode", "half_r", "paired")
KEYS = ("study", "eligible_m5_windows", "action_counts", "candidate_episode_count",
        "m5_episodes", "evaluated", "raw_detected", "c21_detected",
        "both_detected", "nonoverlapping_trades", "partial_hits",
        "exit_reasons", "qualified_signals", "qualifying_observations",
        "trades_with_eligible_m5_history", "A_gross", "B_gross", "A_net", "B_net")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",default="/tmp/v95_hybrid_inventory_20261016.json")
    args=p.parse_args()
    dest=Path(args.output)
    if dest.exists(): p.error("Output already exists")
    found={}
    for rootname in ROOTS:
        root=Path(rootname)
        if not root.is_dir(): continue
        # Avoid scanning large datasets or secrets; inspect names, not file contents.
        for path in root.rglob("*.json"):
            if len(path.parts)>20 or any(part in (".git","node_modules",".venv","secrets",".streamlit") for part in path.parts):
                continue
            if not any(term in path.name.lower() for term in TERMS):
                continue
            try:
                stat=path.stat()
                if stat.st_size>5_000_000: continue
                obj=json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(obj,dict): continue
                found[str(path)]={"size_bytes":stat.st_size,
                    "modified_utc":datetime.fromtimestamp(stat.st_mtime,timezone.utc).isoformat(),
                    "aggregate":{k:obj[k] for k in KEYS if k in obj}}
            except (OSError,UnicodeError,ValueError,TypeError):
                continue
    report={"study":"V9.5 Hybrid research inventory (not a performance meta-analysis)",
            "files_found":len(found),"reports":found,
            "cautions":["Only files with matching names under configured roots are inspected",
                        "Missing files do not imply missing historical experiments",
                        "Metrics from different dates, feeds, and hypothetical positions must not be pooled",
                        "No changes to LIVE or PAPER"]}
    with dest.open("x",encoding="utf-8") as f:json.dump(report,f,indent=2);f.write("\n")
    print(json.dumps({"files_found":len(found),
        "reports":[{"path":k,**v} for k,v in found.items()]},indent=2))
    print("Inventory saved:",dest)
if __name__=="__main__":main()
