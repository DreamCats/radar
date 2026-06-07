from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from radar.core.config import RadarConfig
from radar.core.db import migrate_market_db
from radar.core.models import RawMessage
from radar.core.store import connect, init_db, upsert_messages
from radar.core.usecases.strategy.lead_signals import summarize_lead_signals


def test_summarize_lead_signals_groups_pre_rise_and_limit_like(tmp_path: Path):
    config = RadarConfig(storage={"data_dir": tmp_path, "database": tmp_path / "radar.sqlite3"})
    with connect(config.database_path) as conn:
        init_db(conn)
        upsert_messages(
            conn,
            [
                _message("m1", "2026-06-02T10:00:00"),
                _message("m2", "2026-06-02T14:00:00"),
                _message("m3", "2026-06-03T10:00:00"),
            ],
        )
        _insert_event(conn, "e1", "m1", "2026-06-02T10:00:00", "来源A", "测试股份", "000001.SZ")
        _insert_event(conn, "e2", "m2", "2026-06-02T14:00:00", "来源B", "测试股份", "000001.SZ")
        _insert_event(conn, "e3", "m3", "2026-06-03T10:00:00", "来源C", "涨停股份", "000002.SZ")
        _insert_window(conn, "e1", 1, "20260602", 10, "20260603", 10.5, 0.05, 0.04)
        _insert_window(conn, "e1", 3, "20260602", 10, "20260605", 11, 0.1, 0.08)
        _insert_window(conn, "e2", 1, "20260602", 10, "20260603", 10.5, 0.05, 0.04)
        _insert_window(conn, "e3", 1, "20260603", 20, "20260604", 19, -0.05, -0.06)
    with connect(config.market_database_path) as conn:
        migrate_market_db(conn)
        _insert_daily(conn, "000001.SZ", "20260602", pct_chg=1.2)
        _insert_daily(conn, "000002.SZ", "20260603", pct_chg=9.8)

    result = summarize_lead_signals(config, as_of_date="2026-06-02", days=10, limit=10, source_limit=10)

    assert result.as_of_date == "2026-06-02"
    assert result.day_event_count == 2
    assert result.day_stock_day_count == 1
    assert result.event_count == 2
    assert result.stock_day_count == 1
    assert result.non_hot_event_count == 2
    assert result.non_hot_stock_day_count == 1
    assert result.pre_rise_event_count == 2
    assert result.pre_rise_stock_day_count == 1
    assert result.strong_pre_rise_event_count == 2
    assert result.strong_pre_rise_stock_day_count == 1
    assert result.limit_like_event_count == 0
    assert result.limit_like_stock_day_count == 0
    assert result.samples[0].stock_name == "测试股份"
    assert result.samples[0].signal_label == "强涨前命中"
    assert result.samples[0].event_count == 2
    assert result.samples[0].message_day_pct_chg == 1.2
    assert {item.window_days for item in result.samples[0].windows} == {1, 3}
    assert result.source_stats[0].source_name in {"来源A", "来源B"}
    assert any(item.label == "未明显上涨" and item.window_days == 1 for item in result.buckets)


def _message(message_id: str, message_time: str) -> RawMessage:
    return RawMessage(
        message_id=message_id,
        source="个人群",
        sender=f"sender-{message_id}",
        message_time=datetime.fromisoformat(message_time),
        raw_content="策略测试推荐",
        group_name="策略测试群",
        fetch_time=datetime.fromisoformat("2026-06-02T10:01:00"),
        fetch_window="20260602100000-20260602110000",
    )


def _insert_event(
    conn,
    event_id: str,
    message_id: str,
    message_time: str,
    source_name: str,
    stock_name: str,
    ts_code: str,
) -> None:
    now = datetime.fromisoformat("2026-06-07T12:00:00").isoformat()
    conn.execute(
        """
        INSERT INTO recommendation_events (
            event_id, message_id, source, source_candidate, group_name, category,
            classification_confidence, ts_code, stock_name, action, message_time,
            event_date, extractor_version, anchor_confidence, created_at, updated_at
        ) VALUES (?, ?, '个人群', ?, '策略测试群', 'recommendation', 0.9, ?, ?, 'bullish', ?, ?, 'test', 0.9, ?, ?)
        """,
        (
            event_id,
            message_id,
            source_name,
            ts_code,
            stock_name,
            message_time,
            message_time[:10].replace("-", ""),
            now,
            now,
        ),
    )
    conn.commit()


def _insert_window(
    conn,
    event_id: str,
    window_days: int,
    base_trade_date: str,
    base_close: float,
    target_trade_date: str,
    target_close: float,
    return_rate: float,
    excess_return: float,
) -> None:
    conn.execute(
        """
        INSERT INTO recommendation_backtest_windows (
            event_id, window_days, benchmark_ts_code, base_trade_date, target_trade_date,
            base_close, target_close, return_rate, win, benchmark_return_rate,
            excess_return_rate, status, updated_at
        ) VALUES (?, ?, '000300.SH', ?, ?, ?, ?, ?, ?, 0.01, ?, 'succeeded', ?)
        """,
        (
            event_id,
            window_days,
            base_trade_date,
            target_trade_date,
            base_close,
            target_close,
            return_rate,
            int(return_rate > 0),
            excess_return,
            datetime.fromisoformat("2026-06-07T12:00:00").isoformat(),
        ),
    )
    conn.commit()


def _insert_daily(conn, ts_code: str, trade_date: str, *, pct_chg: float) -> None:
    conn.execute(
        """
        INSERT INTO tushare_history (api_name, ts_code, date_key, data)
        VALUES ('daily', ?, ?, ?)
        """,
        (ts_code, trade_date, json.dumps({"ts_code": ts_code, "trade_date": trade_date, "pct_chg": pct_chg})),
    )
    conn.commit()
