# V9.5 PAPER missed SELL — root-cause update (2026-10-19)

## Grounded evidence
User-provided Oracle journal, 12:50–13:57 UTC, shows collector RECOVERY roughly every 2 minutes with `missing=0` and repeated `WAIT_SELL` decisions. The supplied excerpt has no `WAIT_DATA: stale` entries, but filtered/tail logs cannot prove none occurred outside the excerpt.

- 13:22:52 UTC: SELL proxy 85.5%, M5 bearish=False, enhanced support break=False, H1 bearish=True, support buffer=False -> WAIT_SELL.
- 13:26:53 UTC: SELL proxy 78.2%, M5 bearish=True, support break=False, H1 bearish=True, support buffer=False -> WAIT_SELL.
- 13:46:59 UTC: SELL proxy 76.7%, M5 bearish=False, support break=True, H1 bearish=True, support buffer=False -> WAIT_SELL.
- **13:51:00 UTC: SELL proxy 82.4%, M5 bearish=True, support break=True, H1 bearish=True, support buffer=False -> WAIT_SELL.**
- 13:53:01 UTC: SELL proxy 71.3%, M5 bearish=True, support break=True, H1 bearish=True, support buffer=False -> WAIT_SELL.

## Confirmed from GitHub V9.5 monitor code
Entry condition: `structural_sell and trend and m5_bearish and location and power >= 60`.
`location = (price - older_support) > 1.0 * m15atr`, with `older_support = min(x["l"] for x in m15[-17:-5])`.
Therefore **location=False is a sufficient veto** for 13:51/13:53. The code logs `enhanced_support_break` and `bearish_liquidity_sweep`, but neither is an explicit conjunct in this entry condition. `structural_sell` is an explicit conjunct yet not printed in the journal excerpt, so we cannot establish whether location was the only veto.

## Priority follow-up
Add *research-only* diagnostics logging `structural_sell`, `location`, `older_support`, `m15atr`, `price`, and each required gate, plus a counterfactual detector that records whether removing only the location gate would have produced an otherwise valid PAPER SELL. Compare entry timing, SL/TP, and outcomes on historical complete candles. Do not remove the location gate in the running monitor based on one incident; avoid look-ahead and price chasing.

The stale-data PR #8 remains a separate issue. Do not deploy unverified retry logic as the solution to this SELL decision failure. No changes to V9.4 LIVE.
