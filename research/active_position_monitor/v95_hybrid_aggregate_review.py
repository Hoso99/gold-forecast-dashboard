"""Read-only, privacy-conscious aggregate inspection of Hybrid research JSON.

Prints scalar aggregates and shallow dictionaries; never prints trades, candles,
events, episodes, signals, paths embedded in reports, or arbitrary free text.
"""
import json
from pathlib import Path

REPORTS = [
"/tmp/v95_c21_episode_comparison_01.json",
"/tmp/v95_c22_path_01.json",
"/tmp/v95_c22_comparison_01.json",
"/tmp/v95_c22_reliability_01.json",
"/tmp/v95_c23_ablation_01.json",
"/tmp/v95_c23_34_candles_01.json",
"/tmp/v95_c23_price_outcomes_01.json",
"/tmp/v95_c23_dedup_cost_01.json",
"/tmp/v95_c24_challenger_01.json",
"/home/ubuntu/v95-private-export/v95_m5_m1_trade_comparison_01.json",
"/home/ubuntu/v95-private-export/v95_m5_hybrid_01.json",
"/home/ubuntu/v95-private-export/v95_mtf_exit_study_01.json",
]
BLOCKED = ("token", "secret", "key", "auth", "password", "credential", "address",
           "chat", "email", "phone", "trade", "episode", "event", "candle",
           "row", "minute", "signal", "detail", "sample", "observation",
           "path", "config", "history", "series", "timestamp", "time_utc")
def safe_key(k):
    s=str(k).lower()
    return not any(word in s for word in BLOCKED)
def safe_value(value, depth=0):
    if isinstance(value,bool):return value
    if isinstance(value,(int,float)):return value
    if isinstance(value,dict) and depth<2 and len(value)<=30:
        result={str(k):safe_value(v,depth+1) for k,v in value.items()
                if safe_key(k)}
        return {k:v for k,v in result.items() if v is not None} or None
    return None
def main():
    for path in REPORTS:
        p=Path(path)
        print("\nREPORT:",p.name)
        if not p.is_file():
            print("STATUS: MISSING");continue
        try:
            obj=json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(obj,dict):
                print("STATUS: NON_OBJECT");continue
            print("TOP_LEVEL_KEYS:",", ".join(obj.keys()))
            summary={k:safe_value(v) for k,v in obj.items() if safe_key(k)}
            summary={k:v for k,v in summary.items() if v is not None}
            print("NUMERIC_AGGREGATES:",json.dumps(summary,sort_keys=True,allow_nan=False))
        except (OSError,UnicodeError,ValueError,TypeError) as e:
            print("STATUS: UNREADABLE",type(e).__name__)
if __name__=="__main__":main()
