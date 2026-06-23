from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from radar.core.config import RadarConfig
from radar.core.models import RawMessage
from radar.core.storage import connect, init_db, upsert_messages
from radar.core.tushare.cache import put as put_tushare_cache
from radar.web.server.app import create_app


def test_catalyst_feed_endpoint_detects_stock_names_from_market_cache(tmp_path: Path):
    config = _config(tmp_path, config_dir=tmp_path / "config")
    put_tushare_cache(
        config.market_database_path,
        "stock_basic",
        {},
        [{"ts_code": "300476.SZ", "symbol": "300476", "name": "胜宏科技"}],
    )
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(
            conn,
            [_message("m1", "2026-06-23T09:00:00", raw_content="胜宏科技 300476 在手订单充足，Q3 新产品上量")],
        )
    finally:
        conn.close()

    client = TestClient(create_app(config))
    response = client.get(
        "/api/catalyst/feed",
        params={
            "start_time": "2026-06-23T08:00:00",
            "end_time": "2026-06-23T11:00:00",
            "category_ids": "order_customer",
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["stock_mentions"][0] == {"ts_code": "300476.SZ", "stock_name": "胜宏科技"}


def _config(tmp_path: Path, **overrides) -> RadarConfig:
    return RadarConfig(
        storage={
            "data_dir": tmp_path / "data",
            "database": tmp_path / "radar.sqlite3",
        },
        **overrides,
    )


def _message(
    message_id: str,
    message_time: str,
    *,
    raw_content: str,
    source: str = "个人群",
    group_name: str | None = "东财策略",
    sender: str = "tester",
) -> RawMessage:
    return RawMessage(
        message_id=message_id,
        source=source,
        sender=sender,
        message_time=datetime.fromisoformat(message_time),
        raw_content=raw_content,
        group_name=group_name,
        fetch_time=datetime.fromisoformat("2026-06-04T10:01:00"),
        fetch_window="20260604090000-20260604110000",
    )
