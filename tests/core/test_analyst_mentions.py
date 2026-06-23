from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from radar.core.config import MarketConfig, RadarConfig, StorageConfig
from radar.core.models import MessageClassification, RawMessage
from radar.core.storage import connect, init_db, upsert_message_classifications, upsert_messages
from radar.core.storage.db import migrate_market_db
from radar.core.usecases.analyst_mentions import (
    QUALITY_FLAG_BROAD_LIST,
    list_analyst_stock_mention_evidence,
    list_analyst_stock_mention_message_evidence,
    refresh_analyst_stock_mentions,
    summarize_analyst_stock_mentions,
)
from radar.core.usecases.analyst_mentions.extract import extract_mentions, stock_segment
from radar.core.usecases.stock_evidence_chain.matcher import StockMatcher
from radar.core.usecases.stock_evidence_chain.models import Stock


def test_refresh_analyst_mentions_extracts_stock_mentions_and_backtests(tmp_path: Path):
    config = _config(tmp_path)
    messages = [
        _message("m1", "2026-06-01T09:30:00", "张三", "重点看长江电力和国投电力"),
        _message("m2", "2026-06-03T09:30:00", "张三", "继续关注长江电力"),
        _message("m3", "2026-06-01T10:30:00", "李四", "今天先聊组合仓位"),
    ]
    conn = connect(config.database_path)
    market_conn = connect(config.market_database_path)
    try:
        init_db(conn)
        migrate_market_db(market_conn)
        upsert_messages(conn, messages)
        upsert_message_classifications(
            conn,
            [
                _classification(messages[0], "research", 0.92),
                _classification(messages[1], "research", 0.90),
                _classification(messages[2], "chat", 0.99),
            ],
        )
        _seed_market(market_conn)
    finally:
        conn.close()
        market_conn.close()

    result = refresh_analyst_stock_mentions(
        config,
        as_of=date(2026, 6, 8),
        start_time=datetime.fromisoformat("2026-06-01T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-09T00:00:00"),
        windows=[1],
        cooldown_trade_days=5,
    )

    assert result.scanned_message_count == 2
    assert result.stock_hit_message_count == 2
    assert result.raw_mention_count == 3
    assert result.inserted_mention_count == 3
    assert result.effective_mention_count == 2
    assert result.repeated_mention_count == 1
    assert result.refreshed_count == 2
    assert result.pending_count == 0
    assert result.missing_price_count == 0

    conn = connect(config.database_path)
    try:
        rows = conn.execute(
            """
            SELECT message_id, ts_code, is_effective, dedupe_reason, evidence_snippet
            FROM analyst_stock_mentions
            ORDER BY message_time ASC, ts_code ASC
            """
        ).fetchall()
        assert [(row["message_id"], row["ts_code"], row["is_effective"]) for row in rows] == [
            ("m1", "600886.SH", 1),
            ("m1", "600900.SH", 1),
            ("m2", "600900.SH", 0),
        ]
        assert rows[2]["dedupe_reason"] == "cooldown_repeat"
        assert "长江电力" in rows[1]["evidence_snippet"]
    finally:
        conn.close()

    summary = summarize_analyst_stock_mentions(
        config,
        start_time=datetime.fromisoformat("2026-06-01T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-09T00:00:00"),
        windows=[1],
        min_count=1,
        limit=10,
    )

    assert summary.row_count == 1
    row = summary.rows[0]
    assert row.analyst_display_name == "张三"
    assert row.event_count == 2
    assert row.metrics["sample_count_t1"] == 2
    assert row.metrics["positive_rate_t1"] == 0.5
    assert row.metrics["avg_return_t1"] == 0.025
    assert row.metrics["avg_excess_t1"] == 0.015
    assert "ranking_score_t1" in row.metrics
    assert "ranking_confidence_t1" in row.metrics

    evidence = list_analyst_stock_mention_evidence(
        config,
        start_time=datetime.fromisoformat("2026-06-01T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-09T00:00:00"),
        window=1,
        analyst="张三",
        limit=10,
    )

    assert evidence.row_count == 2
    assert evidence.rows[0].analyst_display_name == "张三"
    assert evidence.rows[0].status == "succeeded"
    assert evidence.rows[0].return_rate == 0.1
    assert "长江电力" in evidence.rows[0].evidence_snippet

    message_evidence = list_analyst_stock_mention_message_evidence(
        config,
        start_time=datetime.fromisoformat("2026-06-01T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-09T00:00:00"),
        window=1,
        analyst="张三",
        limit=10,
    )

    assert message_evidence.row_count == 1
    assert [row.message_id for row in message_evidence.rows] == ["m1"]
    message_row = message_evidence.rows[0]
    assert message_row.stock_count == 2
    assert message_row.metrics["succeeded_count"] == 2
    assert message_row.metrics["avg_return"] == 0.025
    assert "重点看长江电力和国投电力" in message_row.raw_content
    assert {item.stock_name for item in message_row.items} == {"长江电力", "国投电力"}


def test_extract_mentions_filters_broker_source_and_flags_broad_list(tmp_path: Path):
    config = _config(tmp_path)
    messages = [
        _message("source", "2026-06-04T12:00:00", "在水一方", "#东北证券：中船特气产能扩张"),
        _message(
            "broad",
            "2026-06-05T12:00:00",
            "张三",
            "继续看好长江电力、国投电力、中船特气、昊华科技、石英股份、江海股份、南亚新材、圣邦股份",
        ),
    ]
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, messages)
        upsert_message_classifications(
            conn,
            [
                _classification(messages[0], "research", 0.95),
                _classification(messages[1], "research", 0.95),
            ],
        )
        mentions, scanned, stock_hit, broker_filtered = extract_mentions(
            conn,
            StockMatcher(_quality_test_stocks()),
            start_time=datetime.fromisoformat("2026-06-04T00:00:00"),
            end_time=datetime.fromisoformat("2026-06-06T00:00:00"),
            source=None,
            extractor_version="test-v1",
            min_classification_confidence=0.7,
        )
    finally:
        conn.close()

    assert scanned == 2
    assert stock_hit == 2
    assert broker_filtered == 1
    assert not any(item.stock_name == "东北证券" for item in mentions)

    source_mentions = [item for item in mentions if item.message_id == "source"]
    assert [item.stock_name for item in source_mentions] == ["中船特气"]
    assert source_mentions[0].quality_flags == ()

    broad_mentions = [item for item in mentions if item.message_id == "broad"]
    assert len(broad_mentions) == 8
    assert {item.stock_count_in_message for item in broad_mentions} == {8}
    assert all(QUALITY_FLAG_BROAD_LIST in item.quality_flags for item in broad_mentions)


def test_stock_segment_expands_short_heading_to_following_logic():
    text = """
    [太阳]子板块龙头边际变化及预期
    1、中国巨石/国际复材
    a. 交易LDK布看复材/中材，关注光远ipo进度：当前交易主线在msap，终端来看，我们预计近期订单开始起量，价格主升或未至，继续看好PCB链LDK布投资机会。
    b. 交易E布看巨石，价格二阶导有望上行。
    2、东材科技：我们预计公司进海外龙头csp，明年高价值品种量增。
    """

    snippet = stock_segment(text, "国际复材", "301526", "301526.SZ")

    assert "1、中国巨石/国际复材" in snippet
    assert "交易LDK布看复材" in snippet
    assert "继续看好PCB链LDK布投资机会" in snippet
    assert "交易E布看巨石" not in snippet
    assert "2、东材科技" not in snippet


def test_summarize_analyst_mentions_uses_weighted_priority_score(tmp_path: Path):
    config = _config(tmp_path)
    base_time = datetime.fromisoformat("2026-06-01T09:30:00")
    messages = [
        _message(f"rank-{index}", (base_time + timedelta(minutes=index)).isoformat(), "测试分析师", "测试标的")
        for index in range(15)
    ]
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, messages)
        for message in messages[:3]:
            _insert_rank_sample(
                conn,
                message=message,
                analyst_id="hot",
                analyst_name="短样本高收益",
                return_rate=0.40,
                excess_return_rate=0.40,
                positive=True,
            )
        for index, message in enumerate(messages[3:]):
            return_rate = 0.16 if index < 9 else 0.0
            _insert_rank_sample(
                conn,
                message=message,
                analyst_id="steady",
                analyst_name="稳健高胜率",
                return_rate=return_rate,
                excess_return_rate=return_rate,
                positive=return_rate > 0,
            )
        conn.commit()
    finally:
        conn.close()

    summary = summarize_analyst_stock_mentions(
        config,
        start_time=datetime.fromisoformat("2026-06-01T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-02T00:00:00"),
        windows=[5],
        min_count=1,
        limit=10,
    )

    scores = {row.analyst_id: row.metrics["ranking_score_t5"] for row in summary.rows}
    assert scores["steady"] > scores["hot"]
    excess = {row.analyst_id: row.metrics["avg_excess_t5"] for row in summary.rows}
    assert excess["hot"] > excess["steady"]


def test_message_evidence_orders_by_message_time_desc(tmp_path: Path):
    config = _config(tmp_path)
    old_message = _message("old", "2026-06-01T09:30:00", "张三", "早些时候关注长江电力")
    new_message = _message("new", "2026-06-03T09:30:00", "张三", "最新继续关注长江电力")
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, [old_message, new_message])
        _insert_rank_sample(
            conn,
            message=old_message,
            analyst_id="analyst-sort",
            analyst_name="张三",
            return_rate=0.2,
            excess_return_rate=0.2,
            positive=True,
        )
        _insert_rank_sample(
            conn,
            message=new_message,
            analyst_id="analyst-sort",
            analyst_name="张三",
            return_rate=0.01,
            excess_return_rate=0.01,
            positive=True,
        )
        conn.commit()
    finally:
        conn.close()

    evidence = list_analyst_stock_mention_message_evidence(
        config,
        start_time=datetime.fromisoformat("2026-06-01T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-04T00:00:00"),
        window=5,
        analyst="analyst-sort",
        limit=10,
    )

    assert [row.message_id for row in evidence.rows] == ["new", "old"]


def test_summary_latest_event_time_includes_pending_evidence(tmp_path: Path):
    config = _config(tmp_path)
    mature_message = _message("mature", "2026-06-01T09:30:00", "张三", "成熟样本关注长江电力")
    pending_message = _message("pending", "2026-06-10T09:30:00", "张三", "最新证据关注长江电力")
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, [mature_message, pending_message])
        _insert_rank_sample(
            conn,
            message=mature_message,
            analyst_id="analyst-latest",
            analyst_name="张三",
            return_rate=0.2,
            excess_return_rate=0.2,
            positive=True,
        )
        _insert_rank_sample(
            conn,
            message=pending_message,
            analyst_id="analyst-latest",
            analyst_name="张三",
            return_rate=0.0,
            excess_return_rate=0.0,
            positive=False,
            status="pending",
        )
        conn.commit()
    finally:
        conn.close()

    summary = summarize_analyst_stock_mentions(
        config,
        start_time=datetime.fromisoformat("2026-06-01T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-11T00:00:00"),
        windows=[5],
        min_count=1,
        limit=10,
    )

    assert summary.rows[0].latest_event_time == pending_message.message_time
    assert summary.rows[0].metrics["sample_count_t5"] == 1


def test_summary_orders_recent_evidence_before_higher_score(tmp_path: Path):
    config = _config(tmp_path)
    messages = [
        _message("high-old", "2026-06-01T09:30:00", "高分分析师", "历史高分关注长江电力"),
        _message("recent-old", "2026-06-01T10:30:00", "近期分析师", "历史样本关注长江电力"),
        _message("recent-pending", "2026-06-10T09:30:00", "近期分析师", "最新未成熟关注长江电力"),
    ]
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, messages)
        _insert_rank_sample(
            conn,
            message=messages[0],
            analyst_id="high-score",
            analyst_name="高分分析师",
            return_rate=0.4,
            excess_return_rate=0.4,
            positive=True,
        )
        _insert_rank_sample(
            conn,
            message=messages[1],
            analyst_id="recent",
            analyst_name="近期分析师",
            return_rate=0.01,
            excess_return_rate=0.01,
            positive=True,
        )
        _insert_rank_sample(
            conn,
            message=messages[2],
            analyst_id="recent",
            analyst_name="近期分析师",
            return_rate=0.0,
            excess_return_rate=0.0,
            positive=False,
            status="pending",
        )
        conn.commit()
    finally:
        conn.close()

    summary = summarize_analyst_stock_mentions(
        config,
        start_time=datetime.fromisoformat("2026-06-01T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-11T00:00:00"),
        windows=[5],
        min_count=99,
        limit=10,
    )

    assert [row.analyst_id for row in summary.rows] == ["recent", "high-score"]
    scores = {row.analyst_id: row.metrics["ranking_score_t5"] for row in summary.rows}
    assert scores["high-score"] > scores["recent"]


def test_summary_orders_same_pending_date_by_avg_excess(tmp_path: Path):
    config = _config(tmp_path)
    messages = [
        _message("strong-old", "2026-06-01T09:30:00", "强历史", "历史强样本关注长江电力"),
        _message("strong-pending", "2026-06-10T09:30:00", "强历史", "当天未成熟关注长江电力"),
        _message("weak-old", "2026-06-01T10:30:00", "弱历史", "历史弱样本关注长江电力"),
        _message("weak-pending", "2026-06-10T15:30:00", "弱历史", "当天更晚未成熟关注长江电力"),
    ]
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, messages)
        _insert_rank_sample(
            conn,
            message=messages[0],
            analyst_id="strong",
            analyst_name="强历史",
            return_rate=0.2,
            excess_return_rate=0.2,
            positive=True,
        )
        _insert_rank_sample(
            conn,
            message=messages[1],
            analyst_id="strong",
            analyst_name="强历史",
            return_rate=0.0,
            excess_return_rate=0.0,
            positive=False,
            status="pending",
        )
        _insert_rank_sample(
            conn,
            message=messages[2],
            analyst_id="weak",
            analyst_name="弱历史",
            return_rate=-0.1,
            excess_return_rate=-0.1,
            positive=False,
        )
        _insert_rank_sample(
            conn,
            message=messages[3],
            analyst_id="weak",
            analyst_name="弱历史",
            return_rate=0.0,
            excess_return_rate=0.0,
            positive=False,
            status="pending",
        )
        conn.commit()
    finally:
        conn.close()

    summary = summarize_analyst_stock_mentions(
        config,
        start_time=datetime.fromisoformat("2026-06-01T00:00:00"),
        end_time=datetime.fromisoformat("2026-06-11T00:00:00"),
        windows=[5],
        min_count=1,
        limit=10,
    )

    assert [row.analyst_id for row in summary.rows] == ["strong", "weak"]
    assert summary.rows[1].latest_event_time > summary.rows[0].latest_event_time


def _config(tmp_path: Path) -> RadarConfig:
    return RadarConfig(
        storage=StorageConfig(data_dir=tmp_path, database=tmp_path / "radar.sqlite3"),
        market=MarketConfig(database=tmp_path / "market.sqlite3"),
    )


def _message(message_id: str, timestamp: str, sender: str, content: str) -> RawMessage:
    message_time = datetime.fromisoformat(timestamp)
    return RawMessage(
        message_id=message_id,
        source="个人群",
        sender=sender,
        message_time=message_time,
        raw_content=content,
        group_name="投研群",
        fetch_time=message_time,
        fetch_window="test",
    )


def _classification(
    message: RawMessage,
    category: str,
    confidence: float,
) -> MessageClassification:
    now = datetime.fromisoformat("2026-06-01T12:00:00")
    return MessageClassification(
        message_id=message.message_id,
        category=category,  # type: ignore[arg-type]
        confidence=confidence,
        reason="test",
        status="auto",
        classifier_type="rule",
        classifier_version="test-v1",
        created_at=now,
        updated_at=now,
    )


def _seed_market(conn) -> None:
    conn.execute(
        """
        INSERT INTO tushare_cache (key, api_name, fetched_at, data)
        VALUES (?, ?, ?, ?)
        """,
        (
            "stock_basic",
            "stock_basic",
            1,
            json.dumps(
                [
                    {"ts_code": "600900.SH", "symbol": "600900", "name": "长江电力"},
                    {"ts_code": "600886.SH", "symbol": "600886", "name": "国投电力"},
                ],
                ensure_ascii=False,
            ),
        ),
    )
    _insert_prices(
        conn,
        "daily",
        "600900.SH",
        {
            "20260601": 10.0,
            "20260602": 11.0,
            "20260603": 12.0,
            "20260604": 12.5,
            "20260605": 13.0,
            "20260608": 13.5,
        },
    )
    _insert_prices(
        conn,
        "daily",
        "600886.SH",
        {
            "20260601": 20.0,
            "20260602": 19.0,
            "20260603": 19.5,
            "20260604": 20.0,
            "20260605": 20.5,
            "20260608": 21.0,
        },
    )
    _insert_prices(
        conn,
        "index_daily",
        "000300.SH",
        {
            "20260601": 100.0,
            "20260602": 101.0,
            "20260603": 102.0,
            "20260604": 102.5,
            "20260605": 103.0,
            "20260608": 103.5,
        },
    )
    conn.commit()


def _insert_prices(conn, api_name: str, ts_code: str, closes: dict[str, float]) -> None:
    conn.executemany(
        """
        INSERT INTO tushare_history (api_name, ts_code, date_key, data)
        VALUES (?, ?, ?, ?)
        """,
        [
            (api_name, ts_code, trade_date, json.dumps({"close": close}, ensure_ascii=False))
            for trade_date, close in closes.items()
        ],
    )


def _insert_rank_sample(
    conn,
    *,
    message: RawMessage,
    analyst_id: str,
    analyst_name: str,
    return_rate: float,
    excess_return_rate: float,
    positive: bool,
    status: str = "succeeded",
) -> None:
    mention_id = f"{message.message_id}-600900.SH"
    conn.execute(
        """
        INSERT INTO analyst_stock_mentions (
            mention_id, message_id, source, sender, analyst_id, analyst_display_name,
            analyst_alias_key, group_name, category, classification_confidence,
            ts_code, stock_name, symbol, message_time, event_date, evidence_snippet,
            content_fingerprint, extractor_version, stock_count_in_message, quality_flags,
            is_effective, dedupe_key, dedupe_reason, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            mention_id,
            message.message_id,
            message.source,
            message.sender,
            analyst_id,
            analyst_name,
            analyst_id,
            message.group_name,
            "research",
            0.95,
            "600900.SH",
            "长江电力",
            "600900",
            message.message_time.isoformat(),
            message.message_time.date().isoformat(),
            message.raw_content,
            message.message_id,
            "analyst-stock-mention-v1",
            1,
            "[]",
            1,
            mention_id,
            None,
            message.message_time.isoformat(),
            message.message_time.isoformat(),
        ),
    )
    conn.execute(
        """
        INSERT INTO analyst_stock_mention_windows (
            mention_id, window_days, benchmark_ts_code, base_trade_date, target_trade_date,
            base_close, target_close, return_rate, positive, benchmark_base_close,
            benchmark_target_close, benchmark_return_rate, excess_return_rate, status,
            error_message, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            mention_id,
            5,
            "000300.SH",
            "20260601",
            "20260608",
            10.0,
            10.0 * (1 + return_rate),
            return_rate,
            1 if positive else 0,
            100.0,
            100.0,
            0.0,
            excess_return_rate,
            status,
            None,
            message.message_time.isoformat(),
        ),
    )


def _quality_test_stocks() -> list[Stock]:
    return [
        Stock(ts_code="000686.SZ", symbol="000686", name="东北证券"),
        Stock(ts_code="688146.SH", symbol="688146", name="中船特气"),
        Stock(ts_code="600900.SH", symbol="600900", name="长江电力"),
        Stock(ts_code="600886.SH", symbol="600886", name="国投电力"),
        Stock(ts_code="600378.SH", symbol="600378", name="昊华科技"),
        Stock(ts_code="603688.SH", symbol="603688", name="石英股份"),
        Stock(ts_code="002484.SZ", symbol="002484", name="江海股份"),
        Stock(ts_code="688519.SH", symbol="688519", name="南亚新材"),
        Stock(ts_code="300661.SZ", symbol="300661", name="圣邦股份"),
    ]
