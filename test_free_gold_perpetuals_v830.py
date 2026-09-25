from free_gold_perpetuals_v830 import (
    PerpetualConsensus, VenueAudit, parse_binance, parse_bingx, parse_bybit,
    parse_gate, parse_okx)
from free_gold_perpetuals_v90 import collect_free_perpetual_consensus


def test_binance_buy_pressure():
    result = parse_binance(
        {"bids": [["100", "9"]], "asks": [["101", "1"]]},
        [{"m": False, "q": "4", "p": "100.5"}])
    assert result.bias == "BUY PRESSURE"


def test_bybit_sell_pressure():
    result = parse_bybit(
        {"result": {"b": [["100", "1"]], "a": [["101", "9"]]}},
        {"result": {"list": [{"side": "Sell", "size": "4", "price": "100"}]}})
    assert result.bias == "SELL PRESSURE"


def test_okx_neutral():
    result = parse_okx(
        {"data": [{"bids": [["100", "5"]], "asks": [["101", "5"]]}]},
        {"data": [{"side": "buy", "sz": "1", "px": "100"},
                   {"side": "sell", "sz": "1", "px": "100"}]})
    assert result.bias == "NEUTRAL"


def test_bingx_fallback_buy_pressure():
    result = parse_bingx(
        {"data": {"bids": [["100", "9"]], "asks": [["101", "1"]]}},
        {"data": [{"buyerMaker": False, "qty": "4", "price": "100.5"}]})
    assert result.status == "LIVE"
    assert result.bias == "BUY PRESSURE"


def test_gate_fallback_sell_pressure():
    result = parse_gate(
        {"bids": [{"p": "100", "s": 1}],
         "asks": [{"p": "101", "s": 9}]},
        [{"size": -4, "price": "100"}])
    assert result.status == "LIVE"
    assert result.bias == "SELL PRESSURE"


def test_consensus_has_power_fields(monkeypatch):
    rows = {
        "Binance": VenueAudit("Binance", "LIVE", "XAUUSDT", 100, .20, .60,
                              "BUY PRESSURE", 100),
        "Bybit": VenueAudit("Bybit", "LIVE", "XAUUSDT", 100, .10, .50,
                            "BUY PRESSURE", 100),
        "OKX": VenueAudit("OKX", "LIVE", "XAU-USDT-SWAP", 100, -.05, .30,
                          "BUY PRESSURE", 100),
    }
    monkeypatch.setattr(
        "free_gold_perpetuals_v90._collect_slot",
        lambda preferred, fallback=None: rows[preferred])
    result = collect_free_perpetual_consensus()
    assert result.order_flow_decision == "BUY"
    assert result.buying_power > result.selling_power
    assert result.pressure_score > 0
