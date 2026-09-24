from free_gold_perpetuals_v830 import (
    parse_binance, parse_bingx, parse_bybit, parse_gate, parse_okx)


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
