"""V3-A5 append-only SELL signal intake (research only).

Manual one-shot snapshot of GitHub main journal. Does not calculate exits,
submit trades, touch live services, or run a scheduler. A signal is eligible
only if model_time > the frozen 2026-10-16 13:02 UTC baseline AND it was not
present in the anchored 76-record journal. Earlier records are excluded.
"""
import argparse, hashlib, json, os, subprocess
from datetime import datetime, timezone
from pathlib import Path

ANCHOR_COMMIT="df74966d0e4ad1fe5cd8fd3e651e4de5a47502c0"
ANCHOR_SHA="2b0d8a46a0f268b1c84aa6ce8adcd5977195e8a7a98c21ae0ea81a1e5963bd05"
ANCHOR_COUNT=76

def git(repo,*args):
 return subprocess.check_output(["git","-C",str(repo),*args],stderr=subprocess.PIPE)
def iso(t):
 return datetime.fromisoformat(str(t).replace("Z","+00:00")).astimezone(timezone.utc)
def ident(r):
 # Status/exit fields are deliberately excluded: they change after initial signal.
 return json.dumps([r.get("model_time"),r.get("side"),r.get("entry"),r.get("stop_loss"),r.get("take_profit")],separators=(",",":"))
def read_json(data):
 rows=json.loads(data)
 if not isinstance(rows,list):raise ValueError("journal is not an array")
 return rows
def append(path,record):
 line=json.dumps(record,sort_keys=True,separators=(",",":"))+"\n"
 fd=os.open(str(path),os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)
 try:
  os.write(fd,line.encode());os.fsync(fd)
 finally:os.close(fd)
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--repo",default="/tmp/v95-hybrid-c-oct15")
 p.add_argument("--baseline",default="/tmp/v95_scenario_v3a5_baseline_oct16.json")
 p.add_argument("--output-dir",default="/home/ubuntu/v95-private-export/research/v3a5_forward")
 p.add_argument("--fetch",action="store_true",help="fetch origin main (read-only remote)")
 a=p.parse_args()
 repo=Path(a.repo);out=Path(a.output_dir)
 baseline=json.loads(Path(a.baseline).read_text())
 cutoff=iso(baseline["created_at_utc"])
 anchor_raw=git(repo,"show",f"{ANCHOR_COMMIT}:trade_journal_v94.json")
 anchor_hash=hashlib.sha256(anchor_raw).hexdigest()
 if anchor_hash!=ANCHOR_SHA:raise RuntimeError("anchor journal fingerprint mismatch")
 anchor=read_json(anchor_raw)
 if len(anchor)!=ANCHOR_COUNT:raise RuntimeError("anchor record count mismatch")
 anchor_ids={ident(r) for r in anchor}
 if a.fetch:
  subprocess.run(["git","-C",str(repo),"fetch","origin","main"],check=True)
 current_commit=git(repo,"rev-parse","FETCH_HEAD").decode().strip()
 if not current_commit:raise RuntimeError("missing FETCH_HEAD; use --fetch")
 current=read_json(git(repo,"show",f"{current_commit}:trade_journal_v94.json"))
 out.mkdir(parents=True,exist_ok=True)
 state_file=out/"intake_state.json"
 ledger=out/"observations.jsonl"
 if state_file.exists():
  state=json.loads(state_file.read_text())
  if state.get("anchor_commit")!=ANCHOR_COMMIT or state.get("anchor_sha256")!=ANCHOR_SHA or state.get("cutoff")!=cutoff.isoformat():
   raise RuntimeError("intake state incompatible with frozen baseline")
 else:
  # Never start a new state on a moving tip unless anchored by immutable commit.
  state={"anchor_commit":ANCHOR_COMMIT,"anchor_sha256":ANCHOR_SHA,
         "cutoff":cutoff.isoformat(),"seen":sorted(anchor_ids)}
  tmp=state_file.with_suffix(".tmp")
  with tmp.open("x") as f:json.dump(state,f,sort_keys=True);f.write("\n")
  os.replace(tmp,state_file)
 # Recovery: ledger is source of truth after crash between append and state write.
 observed=set()
 if ledger.exists():
  for line in ledger.read_text().splitlines():
   if line.strip():observed.add(json.loads(line)["identity"])
 seen=set(state["seen"])|observed
 counts={"anchor_existing":0,"previously_seen":0,"prebaseline_excluded":0,"new_prospective":0,"invalid":0}
 now=datetime.now(timezone.utc).isoformat()
 for r in current:
  key=ident(r)
  if key in anchor_ids:counts["anchor_existing"]+=1;continue
  if key in seen:counts["previously_seen"]+=1;continue
  try:
   t=iso(r["model_time"]);entry=float(r["entry"]);sl=float(r["stop_loss"]);tp=float(r["take_profit"])
   valid=(str(r.get("side","")).upper()=="SELL" and tp<entry<sl and all(map(lambda x:x==x and abs(x)<1e10,[entry,sl,tp])))
  except (KeyError,ValueError,TypeError,OverflowError):
   valid=False;t=None
  if not valid:category="INVALID_SIGNAL";counts["invalid"]+=1
  elif t<=cutoff:category="PREBASELINE_EXCLUDED";counts["prebaseline_excluded"]+=1
  else:category="PROSPECTIVE_CANDIDATE";counts["new_prospective"]+=1
  # Candidate means first observed in this snapshot; not a validated forward fill.
  record={"first_seen_utc":now,"source_commit":current_commit,
          "identity":key,"classification":category,
          "model_time":r.get("model_time"),"side":r.get("side"),
          "entry":r.get("entry"),"stop_loss":r.get("stop_loss"),
          "take_profit":r.get("take_profit"),
          "source_status_at_first_seen":r.get("status"),
          "shadow_exit_status":"NOT_EVALUATED"}
  append(ledger,record);seen.add(key)
 # Persist only after ledger append. Atomic replace avoids partial state.
 state["seen"]=sorted(seen);state["last_source_commit"]=current_commit;state["last_scan_utc"]=now
 tmp=state_file.with_suffix(".tmp")
 with tmp.open("w") as f:json.dump(state,f,sort_keys=True);f.write("\n");f.flush();os.fsync(f.fileno())
 os.replace(tmp,state_file)
 print(json.dumps({"source_commit":current_commit,"source_records":len(current),
   "anchor_records":len(anchor),"cutoff":cutoff.isoformat(),"counts":counts,
   "ledger":str(ledger),"shadow_exit_engine":"NOT_CONFIGURED",
   "scheduler":"NOT_CONFIGURED"},indent=2))
if __name__=="__main__":main()
