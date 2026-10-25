"""Isolated research-only diagnostic freshness prototype."""

REQUIRED = (
    "diagnostics",
    "research_votes",
    "core_sell_detectors",
    "shadow_entry",
)


def enhance_record(
    record,
    latest_available_m1_utc=None,
    *,
    evaluation_stage=None,
):
    """Annotate a copy of a journal record without modifying its source."""
    result = dict(record)
    result["latest_available_m1_utc"] = latest_available_m1_utc
    result["last_evaluated_m1_utc"] = record.get("m1_bar_start_utc")

    if evaluation_stage == "BEFORE_DIAGNOSTICS":
        freshness = "STALE"
        reason = "EVALUATION_BLOCKED_BEFORE_RECALCULATION"

    elif evaluation_stage == "AFTER_DIAGNOSTICS":
        unavailable = [
            key for key in REQUIRED
            if not isinstance(record.get(key), dict)
            or not record[key]
            or record[key].get("status") == "UNAVAILABLE"
        ]
        freshness = "PARTIAL" if unavailable else "CURRENT"
        reason = (
            "DIAGNOSTIC_COMPONENTS_UNAVAILABLE"
            if unavailable else "DIAGNOSTICS_RECALCULATED"
        )

    else:
        freshness = "UNKNOWN"
        reason = "EVALUATION_STAGE_NOT_RECORDED"

    result["diagnostics_freshness"] = freshness
    result["diagnostics_freshness_reason"] = reason
    result["diagnostics_fresh"] = freshness == "CURRENT"

    if "entry_data_gate" not in result:
        result["entry_data_gate"] = {"status": "NOT_RECORDED"}

    return result


def enhance_verified_record(
    record,
    *,
    current_cycle_id,
    evidence,
    latest_available_m1_utc=None,
):
    """Classify only with matching current-cycle evidence."""
    stage = None

    if (
        isinstance(current_cycle_id, str)
        and bool(current_cycle_id)
        and isinstance(evidence, dict)
        and evidence.get("cycle_id") == current_cycle_id
        and evidence.get("evaluation_stage") in (
            "BEFORE_DIAGNOSTICS",
            "AFTER_DIAGNOSTICS",
        )
    ):
        stage = evidence["evaluation_stage"]

    result = enhance_record(
        record,
        latest_available_m1_utc,
        evaluation_stage=stage,
    )

    result["diagnostics_cycle_verified"] = stage is not None
    return result
