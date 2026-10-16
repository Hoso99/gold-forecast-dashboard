"""Manual-first V3-A5 intake/readiness orchestration (research only).

Designed for an external 15-minute systemd timer, NOT self-scheduling.
No trading, Telegram, collector or live-model changes.
"""
import argparse,datetime,fcntl,json,os,subprocess,sys
from pathlib import Path

ROOT=Path("/home/ubuntu/v95-private-export")
BASELINE=Path("/tmp/v95_scenario_v3a5_baseline_oct16.json")
DB=Path("/home/ubuntu/v95-detector-dev/research/feed_validation/biquote_m1.sqlite3")
OUTPUT=ROOT/"research/v3a5_forward/readiness_reports"
LOCK=ROOT/"research/v3a5_forward/automatic_intake.lock"
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--check-only",action="store_true",help="verify prerequisites; do not fetch or write")
 a=p.parse_args()
 needed=[ROOT/"research/active_position_monitor/v95_scenario_v3a5_intake.py",
 ROOT/"research/active_position_monitor/v95_scenario_v3a5_event_readiness.py",
 BASELINE,DB,Path("/tmp/v95-hybrid-c-oct15/.git")]
 missing=[str(x) for x in needed if not x.exists()]
 print(json.dumps({"mode":"CHECK_ONLY" if a.check_only else "ONE_SHOT",
  "prerequisites_ok":not missing,"missing":missing,
  "timer_managed_externally":True,"shadow_scoring":"DISABLED"}),flush=True)
 if missing:return 2
 if a.check_only:return 0
 LOCK.parent.mkdir(parents=True,exist_ok=True)
 with LOCK.open("a+") as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:
   print("SKIPPED: previous research intake still running",flush=True)
   return 0
  env=os.environ.copy()
  env["PYTHONPATH"]=str(ROOT)+(":"+env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
  first=[sys.executable,"-m","research.active_position_monitor.v95_scenario_v3a5_intake",
         "--fetch","--baseline",str(BASELINE)]
  # A failed fetch must stop the cycle; never silently score a stale journal.
  subprocess.run(first,cwd=ROOT,env=env,check=True,timeout=180)
  OUTPUT.mkdir(parents=True,exist_ok=True)
  stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
  target=OUTPUT/("readiness_"+stamp+".json")
  second=[sys.executable,"-m","research.active_position_monitor.v95_scenario_v3a5_event_readiness",
          "--db",str(DB),"--baseline",str(BASELINE),"--output",str(target)]
  subprocess.run(second,cwd=ROOT,env=env,check=True,timeout=180)
  print("READINESS_REPORT",target,flush=True)
 return 0
if __name__=="__main__":sys.exit(main())
