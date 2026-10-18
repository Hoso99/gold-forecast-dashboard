"""Read-only provenance audit for frozen C2 Raw and V9.5 original head-to-head.

Report metadata and a small sanitized schema sample only; do not export candles,
trade-by-trade sensitive data, private keys, or source code.
"""
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

ROOT=Path("/home/ubuntu/v95-historical-research")
REPORT=ROOT/"derived/c2_raw_vs_scenario_2025_2026_v1.json"
OUT=Path("c2-raw-replay-provenance.json")
KEYWORDS=("c2","raw","reversal","scenario","episode")
EXTS={".py",".md",".json",".jsonl"}
def shape(value):
    if isinstance(value,dict): return {str(k):type(v).__name__ for k,v in list(value.items())[:30]}
    return type(value).__name__

data=json.loads(REPORT.read_text())
episodes=data.get("episodes",[])
sample=[]
for e in episodes[:3]:
    sample.append({"keys":list(e.keys()),"status":e.get("status"),
                   "raw_fields":shape(e.get("raw")),
                   "scenario_fields":shape(e.get("scenario")),
                   "anchor_type":type(e.get("anchor")).__name__})
paths=[]
scan_errors=[]
for base in (ROOT,Path("/home/v95research")):
    try:
        if not base.is_dir():continue
    except OSError:continue
    for here,dirs,files in os.walk(base,followlinks=False,onerror=lambda e:scan_errors.append(type(e).__name__)):
        dirs[:]=[d for d in dirs if d not in (".git","actions-runner",".venv","venv","node_modules","__pycache__")]
        for name in files:
            if not name.lower().endswith(tuple(EXTS)) or not any(k in name.lower() for k in KEYWORDS):continue
            p=Path(here)/name
            try:
                if p.is_symlink() or not p.is_file():continue
                # Metadata only, no file contents; do not export hidden secrets.
                paths.append({"path":str(p),"bytes":p.stat().st_size})
            except OSError:pass
status=Counter(str(e.get("status")) for e in episodes)
out={
 "research_only":True,
 "study":data.get("study"),
 "episode_count":len(episodes),
 "evaluated":data.get("evaluated"),
 "status_counts":dict(status),
 "study_assumptions":{k:data.get(k) for k in ("cost_bps_per_side","stop_distance_usd_per_oz","target_rr","hold_minutes")},
 "paired_net_difference":data.get("paired_net_difference"),
 "raw_exit_reasons":data.get("raw_exit_reasons"),
 "scenario_exit_reasons":data.get("scenario_exit_reasons"),
 "limitations":data.get("limitations"),
 "sample_schema":sample,
 "source_candidates":sorted(paths,key=lambda p:p["path"])[:120],
 "scan_errors":scan_errors[:15],
 "report_sha256":hashlib.sha256(REPORT.read_bytes()).hexdigest(),
 "comparison_status":"NO_FULL_HISTORY_WINNER_UNTIL_FROZEN_C2_IMPLEMENTATION_VERIFIED",
 "no_production_changes":True
}
OUT.write_text(json.dumps(out,indent=2)+"\n")
print("C2_PROVENANCE",json.dumps({k:out[k] for k in ("episode_count","evaluated","status_counts","study_assumptions","comparison_status")}))
print("C2_SOURCE_CANDIDATES",len(paths))
print("C2_PROVENANCE_COMPLETE")
