from __future__ import annotations

import pytest

from radar.core.chat.market_quote_tools import RadarMarketQuoteTools, resolve_quote_symbol
from radar.core.config import RadarConfig
from radar.core.market.quotes import RealtimeQuote


def test_realtime_quote_tool_resolves_index_alias_and_returns_change(tmp_path, monkeypatch):
    config = RadarConfig(storage={"data_dir": tmp_path})
    captured = {}

    def fake_quote(config_arg, *, ts_code, sources):
        captured.update({"config": config_arg, "ts_code": ts_code, "sources": sources})
        return RealtimeQuote(
            ts_code=ts_code,
            source="tencent",
            name="上证指数",
            pre_close=4090.48,
            open=4093.95,
            high=4154.73,
            low=4070.17,
            close=4151.29,
            volume_shares=67_508_104_300,
            amount_yuan=1_556_797_720_000,
            timestamp="20260622143430",
        )

    monkeypatch.setattr("radar.core.chat.market_quote_tools.get_public_realtime_quote", fake_quote)

    result = RadarMarketQuoteTools(config).realtime_quote({"symbol": "上证指数"})

    assert captured == {"config": config, "ts_code": "000001.SH", "sources": ("tencent", "sina")}
    assert result["found"] is True
    assert result["symbol"] == "上证指数"
    assert result["ts_code"] == "000001.SH"
    assert result["source"] == "tencent"
    assert result["name"] == "上证指数"
    assert result["close"] == 4151.29
    assert round(result["change"], 2) == 60.81
    assert round(result["pct_chg"], 2) == 1.49


def test_realtime_quote_tool_accepts_public_code_and_forced_source(tmp_path, monkeypatch):
    captured = {}

    def fake_quote(config_arg, *, ts_code, sources):
        captured.update({"ts_code": ts_code, "sources": sources})
        return None

    monkeypatch.setattr("radar.core.chat.market_quote_tools.get_public_realtime_quote", fake_quote)

    result = RadarMarketQuoteTools(RadarConfig(storage={"data_dir": tmp_path})).realtime_quote(
        {"symbol": "sh000001", "source": "sina"}
    )

    assert captured == {"ts_code": "000001.SH", "sources": ("sina",)}
    assert result == {
        "found": False,
        "symbol": "sh000001",
        "ts_code": "000001.SH",
        "requested_source": "sina",
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("沪指", "000001.SH"),
        ("沪深300", "000300.SH"),
        ("sz399006", "399006.SZ"),
        ("000811.SZ", "000811.SZ"),
    ],
)
def test_resolve_quote_symbol(value, expected):
    assert resolve_quote_symbol(value) == expected
