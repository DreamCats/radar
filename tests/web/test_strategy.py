from __future__ import annotations

from datetime import date, time
from pathlib import Path

from fastapi.testclient import TestClient

from radar.core.config import RadarConfig
from radar.core.tushare import history
from radar.web.server.app import create_app


def test_stock_evidence_chain_latest_endpoint_returns_empty_dashboard(tmp_path: Path):
    client = TestClient(create_app(_config(tmp_path)))
    response = client.get("/api/strategy/evidence-chain/latest", params={"limit": 5})

    assert response.status_code == 200
    data = response.json()
    assert data["item_count"] == 0
    assert data["items"] == []
    assert data["stage_counts"] == {}


def test_strategy_stock_chart_endpoint_reads_local_market_history(monkeypatch, tmp_path: Path):
    config = _config(tmp_path)
    monkeypatch.setattr("radar.core.usecases.stock_evidence_chain.stock_chart._refresh_recent_daily_cache", lambda *args, **kwargs: None)
    daily = history.spec_for("daily")
    assert daily is not None
    history.put_rows(
        config.market_database_path,
        daily,
        [
            _daily("000001.SZ", "20240506", 10, 10.8, 9.8, 10.5, pct_chg=5.0),
            _daily("000001.SZ", "20240507", 10.5, 11.2, 10.1, 11.0, pct_chg=4.76),
            _daily("000001.SZ", "20240508", 11.0, 11.6, 10.7, 10.9, pct_chg=-0.91),
            _daily("000002.SZ", "20240508", 8.0, 8.2, 7.9, 8.1, pct_chg=1.25),
        ],
    )

    client = TestClient(create_app(config))
    response = client.get("/api/strategy/stocks/000001.SZ/chart", params={"days": 2})

    assert response.status_code == 200
    data = response.json()
    assert data["ts_code"] == "000001.SZ"
    assert data["latest_trade_date"] == "20240508"
    assert [item["trade_date"] for item in data["candles"]] == ["20240507", "20240508"]
    assert data["candles"][0]["close"] == 11.0
    assert data["candles"][1]["pct_chg"] == -0.91
    assert data["missing_reason"] is None


def test_strategy_stock_chart_endpoint_returns_empty_when_cache_missing(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("radar.core.usecases.stock_evidence_chain.stock_chart._refresh_recent_daily_cache", lambda *args, **kwargs: None)
    client = TestClient(create_app(_config(tmp_path)))
    response = client.get("/api/strategy/stocks/000001.SZ/chart")

    assert response.status_code == 200
    data = response.json()
    assert data["candles"] == []
    assert data["missing_reason"] == "本地 market.sqlite3 暂无该股票日线缓存"


def test_strategy_stock_chart_endpoint_refreshes_latest_daily_after_close(monkeypatch, tmp_path: Path):
    config = _config(tmp_path)
    daily = history.spec_for("daily")
    assert daily is not None
    history.put_rows(
        config.market_database_path,
        daily,
        [_daily("300024.SZ", "20260605", 14.91, 16.15, 14.24, 15.57, pct_chg=3.39)],
    )
    monkeypatch.setattr("radar.core.tushare.history._today_date", lambda: date(2026, 6, 8))
    monkeypatch.setattr("radar.core.tushare.history._now_time", lambda: time(17, 33))

    calls: list[dict] = []

    def fake_call(config_arg, api_name, params, **kwargs):
        calls.append(params)
        history.put_rows(
            config_arg.market_database_path,
            daily,
            [_daily("300024.SZ", "20260608", 15.12, 16.10, 15.03, 15.90, pct_chg=2.12)],
        )
        return []

    monkeypatch.setattr("radar.core.usecases.stock_evidence_chain.stock_chart.tushare_client.call", fake_call)

    client = TestClient(create_app(config))
    response = client.get("/api/strategy/stocks/300024.SZ/chart", params={"days": 5})

    assert response.status_code == 200
    data = response.json()
    assert calls == [{"ts_code": "300024.SZ", "start_date": "20260606", "end_date": "20260608"}]
    assert data["latest_trade_date"] == "20260608"
    assert [item["trade_date"] for item in data["candles"]] == ["20260605", "20260608"]


def _config(tmp_path: Path) -> RadarConfig:
    return RadarConfig(storage={"data_dir": tmp_path / "data", "database": tmp_path / "radar.sqlite3"})


def _daily(ts_code: str, trade_date: str, open_price: float, high: float, low: float, close: float, *, pct_chg: float | None = None):
    return {
        "ts_code": ts_code,
        "trade_date": trade_date,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "pre_close": open_price,
        "change": close - open_price,
        "pct_chg": pct_chg,
        "vol": 1000,
        "amount": 10000,
    }
