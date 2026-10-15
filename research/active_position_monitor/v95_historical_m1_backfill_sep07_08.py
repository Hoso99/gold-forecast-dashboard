"""Research-only bounded Twelve Data XAU/USD M1 historical backfill.
No trading, no private-data upload, no modifications to existing datasets.
"""
import datetime as dt
import json
import math
import os
import sqlite3
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

UTC=dt.timezone.utc
WINDOWS=[
    ("2026-09-07 00:00:00","2026-09-07 05:59:59"),
    ("2026-09-07 06:00:00","2026-09-07 11:59:59"),
    ("2026-09-07 12:00:00","2026-09-07 17:59:59"),
    ("2026-09-07 18:00:00","2026-09-07 23:59:59"),
    ("2026-09-08 00:00:00","2026-09-08 05:59:59"),
    ("2026-09-08 06:00:00","2026-09-08 11:59:59"),
    ("2026-09-08 12:00:00","2026-09-08 17:59:59"),
    ("2026-09-08 18:00:00","2026-09-08 23:59:59"),
]
KEY=os.environ.get("TWELVE_DATA_API_KEY","").strip()
if not KEY:
    raise SystemExit("API key unavailable to runner; no requests made")
root=Path.home()/".local"/"share"/"v95-1000-signal-backfill"
root.mkdir(parents=True,exist_ok=True,mode=0o700)
os.chmod(root,0o700)
dbpath=root/"historical_m1.sqlite3"
if dbpath.is_symlink():
    raise SystemExit("Refusing symlink database path")
db=sqlite3.connect(dbpath)
os.chmod(dbpath,0o600)
try:
    db.execute("""CREATE TABLE IF NOT EXISTS candles
    (minute INTEGER PRIMARY KEY, open REAL NOT NULL, high REAL NOT NULL,
     low REAL NOT NULL, close REAL NOT NULL, source TEXT NOT NULL)""")
    new=0
    duplicates=0
    rejected=0
    for start,end in WINDOWS:
        params={"symbol":"XAU/USD","interval":"1min","start_date":start,
                "end_date":end,"timezone":"UTC","outputsize":5000,
                "apikey":KEY,"format":"JSON"}
        with urlopen("https://api.twelvedata.com/time_series?"+urlencode(params),timeout=40) as response:
            payload=json.load(response)
        if payload.get("status")=="error" or not isinstance(payload.get("values"),list):
            print("Provider rejected a batch; category:",str(payload.get("code","unknown")))
            raise SystemExit("Backfill stopped: provider rejected a batch")
        accepted=0
        start_dt=dt.datetime.strptime(start,"%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        end_dt=dt.datetime.strptime(end,"%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        for item in payload["values"]:
            try:
                stamp=dt.datetime.strptime(item["datetime"],"%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
                vals=[float(item[k]) for k in ("open","high","low","close")]
                o,h,l,c=vals
                if not(start_dt<=stamp<=end_dt) or stamp.second!=0 or not all(map(math.isfinite,vals)) or not (l<=min(o,c)<=max(o,c)<=h) or min(vals)<=0:
                    raise ValueError("invalid candle")
                minute=int(stamp.timestamp()//60)
                existing=db.execute("SELECT open,high,low,close FROM candles WHERE minute=?",(minute,)).fetchone()
                if existing:
                    if tuple(existing)!=tuple(vals):
                        rejected+=1
                    else:
                        duplicates+=1
                    continue
                db.execute("INSERT INTO candles VALUES (?,?,?,?,?,?)",(minute,o,h,l,c,"TwelveData"))
                accepted+=1
            except (KeyError,ValueError,TypeError,OverflowError):
                rejected+=1
        db.commit()
        new+=accepted
        print(json.dumps({"window_start_utc":start,"returned":len(payload["values"]),"new_valid":accepted}))
    total=db.execute("SELECT COUNT(*) FROM candles").fetchone()[0]
    print(json.dumps({"result":"RESEARCH_ONLY","new_valid":new,"duplicates":duplicates,"rejected_or_conflicting":rejected,"total_private_m1":total,"private_storage":"runner-local only"}))
finally:
    db.close()

# Summarize independently anchored episodes in this private backfill only.
# Counts are NOT automatically additive to the pre-existing 21-episode baseline.
from research.active_position_monitor.v95_mtf_exit_study import load
from research.active_position_monitor.v95_m5_m1_episode_study import analyze
summary=analyze(load(dbpath))
print(json.dumps({k:summary[k] for k in ("m5_candidate_windows","candidate_episodes","confirmed_episodes","unconfirmed_episodes","incomplete_confirmation_windows")},sort_keys=True))
print("Do not add these episodes to the baseline until cross-source time overlap is checked.")
