"""Four-minute isolated Oracle continuity proof; not a 24/7 reliability claim."""
from v95_independent_m1_oracle_proof import run


def main():
    result = run(seconds=245)
    if not result["database_row_count_matches"]:
        raise SystemExit("Isolated SQLite row-count mismatch")
    if result["complete_m1_candles"] < 2:
        raise SystemExit("Insufficient independently validated complete M1 candles")
    if result["validated_m1_gaps"] != 0:
        raise SystemExit("Validated M1 sequence contains gaps")
    print("ORACLE_INDEPENDENT_4MIN_CONTINUITY_OK")


if __name__ == "__main__":
    main()
