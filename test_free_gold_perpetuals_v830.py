from free_gold_perpetuals_v830 import (
    PerpetualConsensus, VenueAudit, parse_binance, parse_bingx, parse_bitget,
    parse_bybit, parse_coinbase, parse_gate, parse_kraken, parse_mexc,
    parse_okx, parse_phemex)
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
        "Gate": VenueAudit("Gate", "LIVE", "XAU_USDT", 100, .20, .60,
                           "BUY PRESSURE", 100),
        "Binance": VenueAudit("Binance", "LIVE", "XAUUSDT", 100, .20, .60,
                              "BUY PRESSURE", 100),
        "Bybit": VenueAudit("Bybit", "LIVE", "XAUUSDT", 100, .10, .50,
                            "BUY PRESSURE", 100),
        "OKX": VenueAudit("OKX", "LIVE", "XAU-USDT-SWAP", 100, .20, .60,
                          "BUY PRESSURE", 100),
        "MEXC": VenueAudit("MEXC", "LIVE", "GOLD_USDT", 100, .20, .60,
                           "BUY PRESSURE", 100),
        "Bitget": VenueAudit("Bitget", "LIVE", "XAUTUSDT", 100, .20, .60,
                             "BUY PRESSURE", 100),
        "Phemex": VenueAudit("Phemex", "LIVE", "XAUUSDT", 100, -.10, .20,
                             "NEUTRAL", 100),
        "Kraken": VenueAudit("Kraken", "LIVE", "XAUT/USD", 100, .20, .60,
                             "BUY PRESSURE", 100),
        "Coinbase": VenueAudit("Coinbase", "LIVE", "PAXG-USD", 100, -.10, -.05,
                               "NEUTRAL", 100),
    }
    monkeypatch.setattr(
        "free_gold_perpetuals_v90._collect_slot",
        lambda preferred, fallback=None: rows[preferred])
    result = collect_free_perpetual_consensus()
    assert result.order_flow_decision == "BUY"
    assert result.pressure_bias == "BUY"
    assert result.buying_power > result.selling_power
    assert result.pressure_score > 0


def test_three_new_venue_parsers():
    mexc = parse_mexc(
        {"bids": [[100, 9]], "asks": [[101, 1]]},
        {"data": [{"T": 1, "v": 4, "p": 100.5}]})
    bitget = parse_bitget(
        {"data": {"b": [[100, 9]], "a": [[101, 1]]}},
        {"data": [{"side": "buy", "size": 4, "price": 100.5}]})
    phemex = parse_phemex(
        {"result": {"book": {"bids": [[1000000, 9]], "asks": [[1010000, 1]]}}},
        {"result": {"trades": [[1, "Buy", 1005000, 4]]}})
    assert mexc.bias == bitget.bias == phemex.bias == "BUY PRESSURE"


def test_gold_token_fallback_parsers():
    kraken = parse_kraken(
        {"result": {"XAUTUSD": {"bids": [[100, 9, 1]],
                                  "asks": [[101, 1, 1]]}}},
        {"result": {"XAUTUSD": [[100.5, 4, 1, "b"]], "last": "1"}})
    coinbase = parse_coinbase(
        {"bids": [[100, 9, 1]], "asks": [[101, 1, 1]]},
        [{"side": "sell", "size": 4, "price": 100.5}])
    assert kraken.bias == coinbase.bias == "BUY PRESSURE"
