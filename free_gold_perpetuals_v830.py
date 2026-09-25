"""Compatibility import for deployments still using the Version 8.3 filename."""

from free_gold_perpetuals_v90 import (  # noqa: F401
    PerpetualConsensus,
    VenueAudit,
    collect_free_perpetual_consensus,
    display_frame,
    parse_binance,
    parse_bingx,
    parse_bybit,
    parse_gate,
    parse_coinbase,
    parse_kraken,
    parse_bitget,
    parse_mexc,
    parse_phemex,
    parse_okx,
)

__all__ = [
    "PerpetualConsensus",
    "VenueAudit",
    "collect_free_perpetual_consensus",
    "display_frame",
    "parse_binance",
    "parse_bingx",
    "parse_bybit",
    "parse_gate",
    "parse_coinbase",
    "parse_kraken",
    "parse_bitget",
    "parse_mexc",
    "parse_phemex",
    "parse_okx",
]
