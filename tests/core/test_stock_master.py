from __future__ import annotations

from pathlib import Path

from radar.core.config import MarketConfig, RadarConfig, StorageConfig
from radar.core.storage import connect, migrate_market_db
from radar.core.tushare.stock_master import refresh_stock_master


def test_refresh_stock_master_replaces_stocks_table(monkeypatch, tmp_path: Path):
    calls: list[tuple[str, bool | None]] = []
    fixtures = {
        "L": [{"ts_code": "002837.SZ", "symbol": "002837", "name": "英维克"}],
        "D": [{"ts_code": "000001.SZ", "symbol": "000001", "name": "平安银行旧名"}],
        "P": [{"ts_code": "920001.BJ", "symbol": "920001", "name": "待上市"}],
    }

    def fake_call(config, api_name, params, fields, *, use_cache=None):
        calls.append((str(params["list_status"]), use_cache))
        return fixtures[str(params["list_status"])]

    monkeypatch.setattr("radar.core.tushare.stock_master.call", fake_call)

    config = _config(tmp_path)
    conn = connect(config.market_database_path)
    try:
        migrate_market_db(conn)
        conn.execute(
            """
            INSERT INTO stocks (ts_code, symbol, name, list_status, updated_at)
            VALUES ('300476.SZ', '300476', '胜宏科技', 'L', datetime('now'))
            """
        )
        conn.commit()
    finally:
        conn.close()

    result = refresh_stock_master(config, force=True)

    assert calls == [("L", False), ("D", False), ("P", False)]
    assert result.fetched_count == 3
    assert result.stored_count == 3
    assert result.listed_count == 1

    conn = connect(config.market_database_path)
    try:
        rows = conn.execute("SELECT ts_code, name, list_status FROM stocks ORDER BY ts_code").fetchall()
    finally:
        conn.close()
    assert [(row["ts_code"], row["name"], row["list_status"]) for row in rows] == [
        ("000001.SZ", "平安银行旧名", "D"),
        ("002837.SZ", "英维克", "L"),
        ("920001.BJ", "待上市", "P"),
    ]


def _config(tmp_path: Path) -> RadarConfig:
    return RadarConfig(
        storage=StorageConfig(data_dir=tmp_path, database=tmp_path / "radar.sqlite3"),
        market=MarketConfig(database=tmp_path / "market.sqlite3"),
    )
