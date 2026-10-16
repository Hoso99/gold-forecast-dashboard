"""Read-only detailed C2.2-C2.4 outcome extraction from Oracle research reports.

Prints aggregate summaries and per-episode numeric diagnostics only. No
changes to source data, live model, paper monitor or detector thresholds.
"""
import json
from pathlib import Path

REPORTS = [
    "/tmp/v95_c21_episode_comparison_01.json",
    "/tmp/v95_c22_comparison_01.json",
    "/tmp/v95_c22_reliability_01.json",
    "/tmp/v95_c23_ablation_01.json",
    "/tmp/v95_c23_34_candles_01.json",
    "/tmp/v95_c23_price_outcomes_01.json",
    "/tmp/v95_c23_dedup_cost_01.json",
    "/tmp/v95_c24_challenger_01.json",
]
PRIVATE = ("token", "secret", "password", "credential", "authorization",
           "api_key", "chat_id", "phone", "email")
def redact_key(k):
    return any(term in str(k).lower() for term in PRIVATE)
def shape(value, depth=0):
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    if isinstance(value, str):
        return value[:180] if depth <= 2 else "[text]"
    if isinstance(value, dict):
        if depth > 5: return "[nested]"
        return {str(k):shape(v,depth+1) for k,v in value.items()
                if not redact_key(k)}
    if isinstance(value, list):
        if depth > 4: return {"count":len(value)}
        if len(value)>35: return {"count":len(value),"first_two":shape(value[:2],depth+1)}
        return [shape(x,depth+1) for x in value]
    return "[unsupported]"
def main():
    for filename in REPORTS:
        path=Path(filename)
        print("\n###",path.name)
        if not path.exists():
            print("MISSING"); continue
        try:
            obj=json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(obj,dict): print("NON-OBJECT");continue
            if "summary" in obj:
                print("SUMMARY",json.dumps(shape(obj["summary"]),sort_keys=True,allow_nan=False))
            if "limitations" in obj:
                print("LIMITATIONS",json.dumps(shape(obj["limitations"]),allow_nan=False))
            episodes=obj.get("episodes")
            if isinstance(episodes,list):
                print("EPISODES",len(episodes))
                # Emit only compact numeric/status episode summaries; avoid raw candle data.
                for idx,ep in enumerate(episodes):
                    if not isinstance(ep,dict):continue
                    fields={}
                    for key,val in ep.items():
                        if redact_key(key):continue
                        if isinstance(val,(bool,int,float)) or val is None:
                            fields[key]=val
                        elif isinstance(val,dict):
                            compact={k:v for k,v in val.items()
                                     if not redact_key(k) and (isinstance(v,(bool,int,float)) or v is None)}
                            if compact:fields[key]=compact
                        elif isinstance(val,str) and key in ("status","action","reason","classification"):
                            fields[key]=val[:80]
                    print("EP",idx+1,json.dumps(fields,sort_keys=True))
            events=obj.get("events")
            if isinstance(events,list):
                print("EVENTS",len(events))
                for idx,event in enumerate(events[:30]):
                    if not isinstance(event,dict):continue
                    fields={k:v for k,v in event.items() if not redact_key(k)
                            and (isinstance(v,(bool,int,float)) or v is None)}
                    print("EVENT",idx+1,json.dumps(fields,sort_keys=True))
        except (OSError,ValueError,TypeError,UnicodeError) as exc:
            print("ERROR",type(exc).__name__)
if __name__=="__main__":main()
