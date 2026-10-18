"""Research-only matched-entry comparison; no changes to live or paper monitors."""
import importlib.util
import json
from pathlib import Path

source_path = Path("research/historical/v95_m1_paper_approx.py")
source = source_path.read_text()
structure = "if m15[-1]['c']>max(x['h'] for x in m15[-4:-1]):"
momentum = """elif (sum(m5[-i]['c']>m5[-i-1]['c'] for i in range(1,5))>=3
                              and m5[-1]['c']>m5[-2]['c'] and h1[-1]['c']>h1[-2]['c']):"""
assert source.count(structure) == source.count(momentum) == 1

confirmed = source.replace(structure, """if (m15[-1]['c']>max(x['h'] for x in m15[-4:-1])
                                +0.25*atr15(aggs[15]['bars'])
                                and m5[-1]['c']>m5[-2]['c']):""").replace(momentum, """elif (sum(m5[-i]['c']>m5[-i-1]['c'] for i in range(1,5))>=4
                              and m5[-1]['c']>m5[-2]['c']
                              and h1[-1]['c']>h1[-2]['c']
                              and c>active['entry']+0.25*atr15(aggs[15]['bars'])):""")

runs = {}
for name, code in [("original", source), ("confirmed", confirmed)]:
    spec = importlib.util.spec_from_loader("audit_" + name, loader=None)
    mod = importlib.util.module_from_spec(spec)
    exec(compile(code, str(source_path), "exec"), mod.__dict__)
    detector = mod.technical_signal
    def sweep75(m1, aggs, fn=detector):
        result = fn(m1, aggs)
        return result if result and result["detector"] == "SWEEP" and result["power"] >= 75 else None
    mod.technical_signal = sweep75
    mod.replay()
    report = json.loads(Path("v95-m1-paper-approx-results.json").read_text())
    runs[name] = {t["entry_utc"]: t for t in report["trades"]}
    print("RUN", name, len(runs[name]), flush=True)

original, challenger = runs["original"], runs["confirmed"]
assert original.keys() == challenger.keys(), "Entry timestamps differ; abort paired analysis"
pairs = []
for timestamp in sorted(original):
    a, b = original[timestamp], challenger[timestamp]
    x, y = a.get("net_r"), b.get("net_r")
    pairs.append({"entry_utc": timestamp, "year": a["year"],
                  "original_outcome": a["outcome"], "confirmed_outcome": b["outcome"],
                  "original_net_r": x, "confirmed_net_r": y,
                  "delta_r": round(y-x, 7) if x is not None and y is not None else None})

def stats(rows):
    complete = [p["delta_r"] for p in rows if p["delta_r"] is not None]
    return {"entries": len(rows), "paired_completed": len(complete),
            "unresolved_pairs": len(rows)-len(complete),
            "mean_delta_r": round(sum(complete)/len(complete), 6) if complete else None,
            "sum_delta_r": round(sum(complete), 6),
            "challenger_better": sum(v > 0 for v in complete),
            "challenger_worse": sum(v < 0 for v in complete),
            "ties": sum(v == 0 for v in complete)}
summary = stats(pairs)
yearly = {str(y): stats([p for p in pairs if p["year"] == y]) for y in range(2020, 2027)}
unresolved = [p for p in pairs if p["delta_r"] is None]
output = {"research_only": True, "not_full_v95_paper": True,
          "warning": "Completed-pair comparison excludes censored outcomes; 2026 was previously examined",
          "summary": summary, "yearly": yearly,
          "unresolved": unresolved, "pairs": pairs}
Path("v95-exit-paired-audit.json").write_text(json.dumps(output, indent=2) + "\n")
print("PAIRED_SUMMARY", json.dumps(summary))
print("YEARLY", json.dumps(yearly))
print("UNRESOLVED", json.dumps(unresolved))
print("PAIRED_AUDIT_COMPLETE")
