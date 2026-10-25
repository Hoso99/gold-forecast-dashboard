
"""Isolated research-only unified journal adapter."""

from unified_freshness import classify_freshness


def enhance_unified_record(
    record,
    *,
    current_cycle_id,
    evidence,
    latest_available_m1_utc=None,
):
    result = dict(record)

    classification = classify_freshness(
        current_cycle_id,
        evidence,
    )

    result.update(classification)

    result["diagnostics_fresh"] = (
        classification["diagnostics_freshness"] == "CURRENT"
    )

    result["latest_available_m1_utc"] = (
        latest_available_m1_utc
    )

    result["last_evaluated_m1_utc"] = (
        record.get("m1_bar_start_utc")
    )

    return result
