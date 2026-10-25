# V9.5 Freshness Instrumentation Plan

Status: ISOLATED RESEARCH ONLY
Deployment: NOT APPROVED

## 1. Cycle initialization

Create one FreshnessEvidence instance per cycle.

Keep evidence separate from persisted trading state.

A market-closed cycle receives fresh empty evidence.

## 2. Evaluation instrumentation

Pass the evidence tracker to evaluate() through
an optional, keyword-only argument.

Preserve the existing three-value return contract.

Do not modify any existing return statements.

## 3. Component completion

After evaluate_optional_h4() succeeds:
- Mark diagnostics completed.
- Mark research_votes completed.

If its existing exception handler runs:
- Mark both components unavailable.

After entry_diagnostics() succeeds:
- Mark shadow_entry completed.

If its existing exception handler runs:
- Mark shadow_entry unavailable.

After detect_core_sell() succeeds:
- Mark core_sell_detectors completed.

Do not add exception handling around core SELL
detectors that would change existing behavior.

## 4. Journal instrumentation

Pass cycle evidence separately to journal_decision().

Add observational freshness metadata only.

Never use freshness classification to authorize,
reject, or modify a trading decision.

If evidence is invalid or missing, report UNKNOWN.

## 5. Timestamp integrity

Do not treat last_bar as proof of recalculation.

Record the actual evaluated M1 candle separately.

Do not claim the latest available market candle
unless it has been independently established.

## 6. Safety validation

Verify:
- All 21 evaluation return statements remain.
- Protective checks retain their original ordering.
- SELL entry conditions remain identical.
- SL/TP calculations remain identical.
- Existing journal fields remain unchanged.
- Telegram behavior remains unchanged.
- V9.4 LIVE remains untouched.
- Running V9.5 PAPER remains untouched.

## 7. Approval boundary

Only modify the isolated candidate after review.

No deployment, service restart, or modification
of the running monitor without separate approval.
