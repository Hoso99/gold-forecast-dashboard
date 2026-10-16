"""V3-A5 prospective shadow readiness and frozen baseline.
RESEARCH ONLY: reads historical journal and M1 source files, writes a new
snapshot at --output with exclusive create. No trading/Telegram/services.
This is NOT an active forward collector or validated forward replay.
"""
import argparse,hashlib,json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from research.active_position_monitor.v95_62_sell_phase2b_features import JOURNAL,SOURCES,minute

RULES={
 "benchmark":"C2 Raw; original research replay, no modification",
 "challenger":"V3-A2 bounded 5-minute",
 "buy_power_threshold":75,
 "max_confirmation_minutes":5,
 "m1_confirmation":"buy>=75, bullish M1 breakout, >=2 bullish of last 3, last close >= third-last close",
 "m5_confirmation":"buy>=75, latest completed UTC-aligned M5 bullish and close above previous M5 high",
 "deadline":"issue hypothetical exit after five completed M1 bars since first C2 exit request; no resets",
 "execution":"hypothetical next available M1 open, no actual fills",
 "protective":"retain original hard SL/TP reference and flag intrabar ambiguity",
 "reporting":"paired R, stop distance, delays, reason, per-episode comparisons, cost sensitivity"
}
def digest(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--output",required=True)
 p.add_argument("--existing-replay",default="/tmp/v95_scenario_v3a2_oct16.json")
 a=p.parse_args()
 dest=Path(a.output)
 if dest.exists():p.error("output exists; do not overwrite prospective baseline")
 now=datetime.now(timezone.utc).isoformat()
 checks=[]
 for path in [JOURNAL,*SOURCES,Path(a.existing_replay)]:
  item={"path":str(path),"exists":path.is_file()}
  if path.is_file():
   item.update(size_bytes=path.stat().st_size,sha256=digest(path))
  checks.append(item)
 if not all(x["exists"] for x in checks):
  print(json.dumps({"ready":False,"files":checks},indent=2));return
 journal=json.loads(JOURNAL.read_text())
 sells=[(i,r) for i,r in enumerate(journal,1) if str(r.get("side","")).upper()=="SELL"]
 replay=json.loads(Path(a.existing_replay).read_text())
 if replay.get("parameters",{}).get("threshold")!=75 or 5 not in replay.get("parameters",{}).get("limits",[]):
  raise ValueError("Replay does not match frozen 75% / 5-minute V3-A2 rules")
 if len(replay.get("signals",[]))!=len(sells):
  raise ValueError("Journal and replay signal counts differ; cannot freeze baseline")
 signal_times=[minute(r["model_time"]) for _,r in sells if r.get("model_time")]
 baseline={
  "study":"V3-A5 prospective shadow baseline, readiness only",
  "created_at_utc":now,
  "baseline_signal_count":len(sells),
  "baseline_last_signal_index":max((i for i,_ in sells),default=None),
  "baseline_max_model_minute_utc":max(signal_times,default=None),
  "baseline_model_times":[{"index":i,"model_time":r.get("model_time")} for i,r in sells],
  "files":checks,
  "frozen_rules":RULES,
  "prospective_eligibility":"Only new SELL signal identities with model_time later than baseline_max_model_minute_utc; record all exclusions and missing bars",
  "readiness":{"files_present":True,"replay_matches_frozen_rules":True,
               "prospective_collector_configured":False,
               "live_data_freshness_verified":False,
               "automatic_scheduler_configured":False},
  "limitations":[
   "This command snapshots readiness only; it does not collect new signals or candles",
   "Historical signal index is not a stable ID if journal is rewritten; use model_time plus entry/SL/TP in later collector",
   "Existing M1 files may be stale; no freshness claim made",
   "Frozen baseline records source hashes to detect changes, not enforce immutability",
   "Future forward runs require append-only observations and independent audit",
   "No live V9.4, V9.5 PAPER, C2 Raw, Telegram, SL/TP or services modified"
  ]}
 with dest.open("x",encoding="utf-8") as f:json.dump(baseline,f,indent=2);f.write("\n")
 print(json.dumps({"baseline_created":str(dest),
                   "baseline_signal_count":len(sells),
                   "last_signal_index":baseline["baseline_last_signal_index"],
                   "latest_model_minute_utc":baseline["baseline_max_model_minute_utc"],
                   "frozen_threshold":75,"frozen_confirmation_minutes":5,
                   "file_checks":checks,
                   "collector_configured":False,"scheduler_configured":False},indent=2))
if __name__=="__main__":main()
