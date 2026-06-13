from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from radar.core.config import RadarConfig
from radar.core.tushare import history
from radar.web.server.app import create_app


def test_strategy_stock_financials_endpoint_reads_local_tushare_history(tmp_path: Path):
    config = _config(tmp_path)
    for api_name, row in [
        (
            "income",
            {
                "ts_code": "000001.SZ",
                "end_date": "20240331",
                "ann_date": "20240425",
                "f_ann_date": "20240425",
                "report_type": "1",
                "revenue": 1_000_000_000,
                "n_income_attr_p": 120_000_000,
            },
        ),
        (
            "balancesheet",
            {
                "ts_code": "000001.SZ",
                "end_date": "20240331",
                "ann_date": "20240425",
                "report_type": "1",
                "accounts_receiv": 300_000_000,
                "inventories": 200_000_000,
            },
        ),
        (
            "cashflow",
            {
                "ts_code": "000001.SZ",
                "end_date": "20240331",
                "ann_date": "20240425",
                "report_type": "1",
                "n_cashflow_act": 90_000_000,
            },
        ),
        (
            "fina_indicator",
            {
                "ts_code": "000001.SZ",
                "end_date": "20240331",
                "ann_date": "20240425",
                "or_yoy": 35.1,
                "netprofit_yoy": 48.2,
                "grossprofit_margin": 28.5,
                "roe": 9.4,
                "debt_to_assets": 42.3,
            },
        ),
    ]:
        spec = history.spec_for(api_name)
        assert spec is not None
        history.put_rows(config.market_database_path, spec, [row])

    client = TestClient(create_app(config))
    response = client.get("/api/strategy/stocks/000001.SZ/financials")

    assert response.status_code == 200
    data = response.json()
    assert data["ts_code"] == "000001.SZ"
    assert data["status"] == "已接 Tushare"
    assert data["tone"] == "ready"
    assert data["latest_period"] == "20240331"
    assert data["latest_ann_date"] == "20240425"
    assert {"label": "营收", "value": "10.00亿", "tone": None} in data["metrics"]
    assert any("营业收入 10.00亿" in line and "归母净利 1.20亿" in line for line in data["lines"])
    assert any("经营现金流 0.90亿" in line and "0.75x" in line for line in data["lines"])


def test_strategy_stock_financials_endpoint_returns_missing_when_no_data(tmp_path: Path):
    client = TestClient(create_app(_config(tmp_path)))
    response = client.get("/api/strategy/stocks/000001.SZ/financials")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "暂无财报"
    assert data["tone"] == "missing"
    assert data["latest_period"] is None
    assert data["missing_reason"] == "Tushare 暂无该股票近年财报数据或本地配置暂不可用。"


def _config(tmp_path: Path) -> RadarConfig:
    return RadarConfig(storage={"data_dir": tmp_path / "data", "database": tmp_path / "radar.sqlite3"})
