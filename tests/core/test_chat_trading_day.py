from __future__ import annotations

from datetime import date

from radar.core.chat.trading_day import build_trading_day_prompt, today_trading_day_status
from radar.core.config import RadarConfig


def test_trading_day_prompt_reads_tushare_trade_cal(monkeypatch):
    captured = {}

    def fake_call(config, api_name, params=None, fields=None, cache_ttl=None):
        captured.update(
            {
                "api_name": api_name,
                "params": params,
                "fields": fields,
                "cache_ttl": cache_ttl,
            }
        )
        return [{"cal_date": "20260609", "is_open": 1}]

    monkeypatch.setattr("radar.core.chat.trading_day.call", fake_call)

    config = RadarConfig()

    assert today_trading_day_status(config, today=date(2026, 6, 9)) is True
    assert build_trading_day_prompt(config, today=date(2026, 6, 9)) == "今日是否 A 股交易日：是"
    assert captured == {
        "api_name": "trade_cal",
        "params": {"exchange": "SSE", "start_date": "20260609", "end_date": "20260609"},
        "fields": "cal_date,is_open",
        "cache_ttl": 3600,
    }


def test_trading_day_prompt_returns_unknown_when_tushare_unconfigured():
    assert build_trading_day_prompt(RadarConfig(), today=date(2026, 6, 9)) == "今日 A 股交易日状态：未知"
