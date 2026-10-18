"""Single-run, read-only original-vs-C2 evidence audit. Never fabricate matched results."""
import json,collections,hashlib
from pathlib import Path
ROOT=Path("/home/ubuntu/v95-historical-research")
REPORT=ROOT/"derived/c2_raw_vs_scenario_2025_2026_v1.json"
OUT=Path("v95-c2-one-go-decision.json")
ORIGINAL={"completed":138,"entries":145,"censored":7,"sum_net_r":-6.214502,"profit_factor":0.856241,"win_rate":0.3043,
          "provenance":"v95 adaptive matched audit run 39128223687; M1 technical approximation"}
dbnames=["twelve_xauusd_m1.sqlite3","twelve_xauusd_m1_2021_2022.sqlite3","twelve_xauusd_m1_2022_2023.sqlite3","twelve_xauusd_m1_2023_2024.sqlite3","twelve_xauusd_m1_2024_2025.sqlite3","twelve_xauusd_m1_2025_2026.sqlite3","twelve_xauusd_m1_2026_partial.sqlite3"]
result={"research_only":True,"deployment_changes":False,"original":ORIGINAL,"databases":[{"name":n,"available":(ROOT/n).is_file()} for n in dbnames],
        "decision":"NOT_PROVEN","promote_c2_raw":False}
try:
 data=json.loads(REPORT.read_text())
 episodes=data.get("episodes",[])
 valid=[x for x in episodes if x.get("status")=="EVALUATED"]
 result["c2_raw"]={"study":data.get("study"),"episode_count":len(episodes),"evaluated":len(valid),
                  "status_counts":dict(collections.Counter(str(x.get("status")) for x in episodes)),
                  "study_assumptions":{k:data.get(k) for k in ("cost_bps_per_side","stop_distance_usd_per_oz","target_rr","hold_minutes")},
                  "raw_exit_reasons":data.get("raw_exit_reasons"),
                  "scenario_difference":data.get("paired_net_difference"),
                  "report_sha256":hashlib.sha256(REPORT.read_bytes()).hexdigest()}
 # Aggregate C2 Raw returns using existing source-recorded exits. These are
 # hypothetical overlapping episodes, NOT V9.5 matched trade outcomes.
 raw=[x["raw"]["net_usd_per_oz"] for x in valid if isinstance(x.get("raw"),dict) and isinstance(x["raw"].get("net_usd_per_oz"),(int,float))]
 if raw:
  gains=sum(x for x in raw if x>0);losses=-sum(x for x in raw if x<0)
  result["c2_raw"]["episode_metrics"]={"n":len(raw),"sum_usd_per_oz":round(sum(raw),6),
    "mean_usd_per_oz":round(sum(raw)/len(raw),6),
    "positive_fraction":round(sum(x>0 for x in raw)/len(raw),6),
    "profit_factor":round(gains/losses,6) if losses else None,
    "warning":"Hypothetical potentially overlapping episodes; NOT trade-level portfolio PF"}
 # Can entries be matched without inventing timestamps? Both must have exact
 # compatible entry keys and same entry policy, which the studies do not.
 result["entry_parity"]={"v95_entry":"technical sweep75 M1 signal close with structure/ATR stop",
    "c2_entry":"hypothetical next M1 open after M5 anchor with fixed $15 stop",
    "matched_entries_verified":False}
 result["decision_reason"]="C2 episode-level outcomes cannot be compared with original trade-level outcomes as if matched; no verified executable C2 replay across all seven years."
except (OSError,ValueError,TypeError,KeyError) as exc:
 result["error"]=type(exc).__name__
 result["decision_reason"]="Unable to validate C2 episode report"
OUT.write_text(json.dumps(result,indent=2)+"\n")
print("ORIGINAL_VS_C2_ONE_GO",json.dumps({k:result.get(k) for k in ("decision","promote_c2_raw","decision_reason")}))
print("C2_EPISODE_METRICS",json.dumps(result.get("c2_raw",{}).get("episode_metrics")))
print("NO_LIVE_OR_PAPER_CHANGES")
