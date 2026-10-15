"""V9.5 research-only continuity simulation for three October 14 outage slots.

This is a *coverage simulation*, NOT historical Biquote replay. It never
generates prices/candles or writes to any database. Each scenario assumes
the independent collector actually recorded a validated Biquote candle.
"""
import datetime as dt
import json

UTC = dt.timezone.utc
OUTAGES = (
    "2026-10-14T10:23:00+00:00",
    "2026-10-14T11:51:00+00:00",
    "2026-10-14T19:59:00+00:00",
)


def minute(value):
    stamp = dt.datetime.fromisoformat(value)
    if stamp.tzinfo is None or stamp.utcoffset() != dt.timedelta(0):
        raise ValueError("UTC timestamps required")
    if stamp.second or stamp.microsecond:
        raise ValueError("Minute alignment required")
    return stamp.astimezone(UTC).isoformat()


def continuity(primary_minutes, independent_minutes, expected_minutes=OUTAGES):
    """Report whether a genuinely independent archive could cover primary gaps.

    Input sets represent verified minute timestamps only; this does not verify
    OHLC authenticity. The live repair system must independently validate
    Biquote provenance and candle quality before accepting any records.
    """
    primary = {minute(x) for x in primary_minutes}
    independent = {minute(x) for x in independent_minutes}
    expected = [minute(x) for x in expected_minutes]
    report = []
    for stamp in expected:
        report.append({
            "minute_utc": stamp,
            "primary_present": stamp in primary,
            "independent_present": stamp in independent,
            "continuity_possible": stamp in primary or stamp in independent,
        })
    return {"mode": "SIMULATION_ONLY_NO_PRICE_DATA",
            "results": report,
            "passed": sum(item["continuity_possible"] for item in report),
            "total": len(report)}


def main():
    # Deliberately simulates primary collector dropping all three minutes,
    # while the independent collector remains connected for each one.
    outcome = continuity([], OUTAGES)
    print(json.dumps(outcome, indent=2))
    print("NOTE: This is a hypothetical connectivity test, NOT proof that "
          "the actual October 14 candles existed or were captured.")


if __name__ == "__main__":
    main()
