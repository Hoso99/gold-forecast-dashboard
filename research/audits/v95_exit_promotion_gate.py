"""Offline V9.5 exit research quality gates; never authorizes deployment."""
from __future__ import annotations
import json
from pathlib import Path


def assess(report: dict) -> dict:
    if report.get("status") != "EXPLORATORY_NOT_LIVE":
        return {"decision": "NO_PROMOTION", "reason": "Replay produced no comparable trades"}
    periods=report.get("periods", {})
    result={}
    for name in ("development","holdout"):
        period=periods.get(name,{})
        a=period.get("fixed_2r",{})
        b=period.get("dynamic_reversal_partial",{})
        n=a.get("n",0)
        if n != b.get("n"):
            return {"decision":"NO_PROMOTION","reason":"Unpaired strategy sample counts"}
        x=a.get("mean_net_r")
        y=b.get("mean_net_r")
        result[name]={"n":n,"baseline_mean_net_r":x,
                      "dynamic_mean_net_r":y,
                      "delta_mean_net_r":round(y-x,5) if x is not None and y is not None else None,
                      "early_exits":b.get("early_exits",0),
                      "partials_not_reported":True}
    holdout=result["holdout"]
    reasons=[
        "Open-stamped M1 timestamps not provider-verified",
        "No actual V9.4 entry, adaptive ATR, Biquote state, or broker fills",
        "Illustrative execution costs and stop-first intrabar assumptions",
        "Missing trade-level paired outcomes and confidence intervals",
        "M5/M15/H1 rules are unvalidated hypotheses",
    ]
    if holdout["n"]<30:
        reasons.append("Fewer than 30 non-overlapping holdout trades")
    if holdout["delta_mean_net_r"] is None or holdout["delta_mean_net_r"]<=0:
        reasons.append("No observed positive holdout mean-R improvement")
    return {"decision":"NO_PROMOTION","research_status":"SCREENING_ONLY",
            "periods":result,"blocking_reasons":reasons,
            "next_steps":["Validate M1 timestamp semantics and feed integrity",
                          "Replay actual logged SELL entries and risk settings",
                          "Export per-trade paired outcomes and exit timestamps",
                          "Test execution costs and slippage sensitivity",
                          "Evaluate independent untouched forward holdout"]}


def main():
    p=Path("research-reports/v95_dynamic_exit_replay.json")
    print(json.dumps(assess(json.loads(p.read_text())),indent=2))


if __name__=="__main__":
    main()
