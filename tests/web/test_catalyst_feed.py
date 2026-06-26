from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from radar.core.config import RadarConfig
from radar.core.models import RawMessage
from radar.core.storage import connect, init_db, migrate_market_db, upsert_messages
from radar.web.server.app import create_app


def test_catalyst_feed_endpoint_detects_stock_names_from_market_master(tmp_path: Path):
    config = _config(tmp_path, config_dir=tmp_path / "config")
    _seed_stocks(
        config,
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


def test_catalyst_feed_endpoint_detects_three_character_stock_names(tmp_path: Path):
    config = _config(tmp_path, config_dir=tmp_path / "config")
    _seed_stocks(
        config,
        [{"ts_code": "002837.SZ", "symbol": "002837", "name": "英维克"}],
    )
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(
            conn,
            [
                _message(
                    "m1",
                    "2026-06-23T09:00:00",
                    raw_content="绿色AI向前一步，英特尔联合英维克、嘉实多发布单相冷板液冷工质测试验证成果",
                )
            ],
        )
    finally:
        conn.close()

    client = TestClient(create_app(config))
    response = client.get(
        "/api/catalyst/feed",
        params={
            "start_time": "2026-06-23T08:00:00",
            "end_time": "2026-06-23T11:00:00",
            "category_ids": "technology_product",
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["stock_mentions"] == [{"ts_code": "002837.SZ", "stock_name": "英维克"}]


def test_catalyst_feed_endpoint_keeps_context_required_stock_names_strict(tmp_path: Path):
    config = _config(tmp_path, config_dir=tmp_path / "config")
    _seed_stocks(
        config,
        [{"ts_code": "300024.SZ", "symbol": "300024", "name": "机器人"}],
    )
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(
            conn,
            [
                _message(
                    "m1",
                    "2026-06-23T09:00:00",
                    raw_content="人形机器人客户验证加速，产业趋势继续扩散",
                )
            ],
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
    assert data["items"] == []


def test_catalyst_feed_endpoint_hides_items_without_stock_mentions(tmp_path: Path):
    config = _config(tmp_path, config_dir=tmp_path / "config")
    _seed_stocks(
        config,
        [{"ts_code": "300476.SZ", "symbol": "300476", "name": "胜宏科技"}],
    )
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(
            conn,
            [
                _message("m1", "2026-06-23T09:00:00", raw_content="在手订单充足，Q3 交付节奏加快"),
                _message("m2", "2026-06-23T09:10:00", raw_content="胜宏科技在手订单充足，Q3 交付节奏加快"),
            ],
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
    assert [item["message_id"] for item in data["items"]] == ["m2"]
    assert data["summary"]["total_items"] == 1
    assert data["summary"]["available_total_items"] == 1
    assert data["summary"]["category_counts"] == {"order_customer": 1}
    assert data["summary"]["term_counts"]["order_customer"]["在手订单"] == 1


def test_catalyst_feed_endpoint_term_filter_keeps_base_term_counts(tmp_path: Path):
    config = _config(tmp_path, config_dir=tmp_path / "config")
    _seed_stocks(
        config,
        [{"ts_code": "300476.SZ", "symbol": "300476", "name": "胜宏科技"}],
    )
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(
            conn,
            [
                _message("m1", "2026-06-23T09:00:00", raw_content="胜宏科技 涨价 提价"),
                _message("m2", "2026-06-23T09:01:00", raw_content="胜宏科技 提价"),
                _message("m3", "2026-06-23T09:02:00", raw_content="胜宏科技 涨价"),
            ],
        )
    finally:
        conn.close()

    client = TestClient(create_app(config))
    response = client.get(
        "/api/catalyst/feed",
        params={
            "start_time": "2026-06-23T08:00:00",
            "end_time": "2026-06-23T11:00:00",
            "category_ids": "price_supply",
            "term_category_id": "price_supply",
            "term": "提价",
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total_items"] == 2
    assert data["summary"]["available_total_items"] == 3
    assert data["summary"]["category_counts"]["price_supply"] == 3
    assert data["summary"]["term_counts"]["price_supply"]["提价"] == 2
    assert data["summary"]["term_counts"]["price_supply"]["涨价"] == 2
    assert {item["message_id"] for item in data["items"]} == {"m1", "m2"}


def test_catalyst_feed_endpoint_dedupes_same_content_from_different_senders(tmp_path: Path):
    config = _config(tmp_path, config_dir=tmp_path / "config")
    _seed_stocks(
        config,
        [{"ts_code": "300476.SZ", "symbol": "300476", "name": "胜宏科技"}],
    )
    content = "胜宏科技在手订单充足，Q3 交付节奏加快"
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(
            conn,
            [
                _message("m1", "2026-06-23T09:00:00", raw_content=content, sender="alice"),
                _message("m2", "2026-06-23T09:10:00", raw_content=content, sender="bob"),
            ],
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
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["duplicate_count"] == 2
    assert {source["sender"] for source in item["duplicate_sources"]} == {"alice", "bob"}
    assert data["summary"]["total_items"] == 1
    assert data["summary"]["total_messages"] == 2
    assert data["summary"]["duplicate_messages"] == 1


def test_catalyst_feed_endpoint_dedupes_wechat_decorative_tokens(tmp_path: Path):
    config = _config(tmp_path, config_dir=tmp_path / "config")
    _seed_stocks(
        config,
        [{"ts_code": "300476.SZ", "symbol": "300476", "name": "胜宏科技"}],
    )
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(
            conn,
            [
                _message("m1", "2026-06-23T09:00:00", raw_content="胜宏科技在手订单充足，Q3 交付节奏加快"),
                _message("m2", "2026-06-23T09:10:00", raw_content="胜宏科技在手订单充足，[玫瑰]Q3 交付节奏加快"),
            ],
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
    assert len(data["items"]) == 1
    assert data["items"][0]["duplicate_count"] == 2


def test_catalyst_feed_endpoint_dedupes_long_content_with_short_followup(tmp_path: Path):
    config = _config(tmp_path, config_dir=tmp_path / "config")
    _seed_stocks(
        config,
        [{"ts_code": "300476.SZ", "symbol": "300476", "name": "胜宏科技"}],
    )
    main_content = (
        "胜宏科技在手订单充足，Q3 交付节奏加快，海外客户验证推进，"
        "服务器 PCB 需求延续，产能利用率维持高位，后续订单兑现值得跟踪。"
    )
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(
            conn,
            [
                _message("m1", "2026-06-23T09:00:00", raw_content=main_content, sender="alice"),
                _message("m2", "2026-06-23T09:00:10", raw_content="订单上调了", sender="alice"),
                _message("m3", "2026-06-23T09:10:00", raw_content=main_content, sender="bob"),
            ],
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
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["duplicate_count"] == 2
    assert sorted(source["message_count"] for source in item["duplicate_sources"]) == [1, 2]


def _config(tmp_path: Path, **overrides) -> RadarConfig:
    return RadarConfig(
        storage={
            "data_dir": tmp_path / "data",
            "database": tmp_path / "radar.sqlite3",
        },
        **overrides,
    )


def _seed_stocks(config: RadarConfig, rows: list[dict[str, str]]) -> None:
    conn = connect(config.market_database_path)
    try:
        migrate_market_db(conn)
        conn.executemany(
            """
            INSERT INTO stocks (ts_code, symbol, name, list_status, updated_at)
            VALUES (?, ?, ?, 'L', datetime('now'))
            """,
            [(row["ts_code"], row["symbol"], row["name"]) for row in rows],
        )
        conn.commit()
    finally:
        conn.close()


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
