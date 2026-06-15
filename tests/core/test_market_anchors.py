from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from radar.core.config import RadarConfig, RadarSecrets
from radar.core.market import (
    ensure_market_anchors,
    list_market_anchors,
    refresh_market_anchor_derivatives,
    refresh_market_anchors,
)


def test_refresh_market_anchors_builds_dictionary(tmp_path: Path):
    calls: list[tuple[str, dict[str, Any] | None, str | list[str] | None]] = []

    def fake_call(config, api_name, params, fields):
        calls.append((api_name, params, fields))
        return _rows(api_name)

    result = refresh_market_anchors(
        _config(tmp_path),
        trade_date="20260604",
        tushare_call=fake_call,
    )

    assert result.anchor_count == 7
    assert result.member_count == 7
    assert result.failed_sources == {}
    assert result.source_counts == {
        "dc_concept": 1,
        "dc_concept_cons": 2,
        "kpl_list": 1,
        "kpl_concept_cons": 1,
        "tdx_index": 2,
    }
    assert [call[0] for call in calls] == [
        "dc_index",
        "dc_member",
        "kpl_list",
        "kpl_concept_cons",
        "tdx_index",
    ]

    anchors = list_market_anchors(_config(tmp_path), trade_date="20260604", limit=20)
    names = {anchor.name for anchor in anchors}
    assert {"人形机器人", "机器人", "通达信机器人", "电机", "算力"} <= names

    conn = sqlite3.connect(tmp_path / "market.sqlite3")
    try:
        member_rows = conn.execute(
            "SELECT ts_code, stock_name, reason FROM market_anchor_members ORDER BY ts_code, stock_name"
        ).fetchall()
    finally:
        conn.close()
    assert ("603915.SH", "国茂股份", None) in member_rows
    assert ("002164.SZ", "宁波东力", None) in member_rows


def test_refresh_market_anchors_rebuilds_current_and_spans(tmp_path: Path):
    config = _config(tmp_path)
    refresh_market_anchors(config, trade_date="20260604", tushare_call=lambda _config, api, _params, _fields: _rows(api))
    refresh_market_anchors(config, trade_date="20260605", tushare_call=lambda _config, api, _params, _fields: _rows(api))

    conn = sqlite3.connect(tmp_path / "market.sqlite3")
    try:
        current = conn.execute(
            """
            SELECT anchor_key, anchor_name, member_source, ts_code, latest_trade_date, reason
            FROM market_anchor_current_members
            WHERE anchor_key = 'dc_concept:000084.DC' AND ts_code = '603915.SH'
            """
        ).fetchone()
        span = conn.execute(
            """
            SELECT anchor_key, ts_code, first_seen_date, last_seen_date, seen_days, latest_reason
            FROM market_anchor_member_spans
            WHERE anchor_key = 'dc_concept:000084.DC' AND ts_code = '603915.SH'
            """
        ).fetchone()
    finally:
        conn.close()

    assert current == ("dc_concept:000084.DC", "人形机器人", "dc_concept_cons", "603915.SH", "20260605", None)
    assert span == ("dc_concept:000084.DC", "603915.SH", "20260604", "20260605", 2, None)


def test_refresh_market_anchor_derivatives_can_rebuild_existing_raw(tmp_path: Path):
    config = _config(tmp_path)
    refresh_market_anchors(config, trade_date="20260604", tushare_call=lambda _config, api, _params, _fields: _rows(api))

    conn = sqlite3.connect(tmp_path / "market.sqlite3")
    try:
        conn.execute("DELETE FROM market_anchor_current_members")
        conn.execute("DELETE FROM market_anchor_member_spans")
        conn.commit()
    finally:
        conn.close()

    result = refresh_market_anchor_derivatives(config)

    assert result.latest_trade_date == "20260604"
    assert result.current_count == 7
    assert result.span_count == 7


def test_refresh_market_anchors_replaces_same_trade_date(tmp_path: Path):
    config = _config(tmp_path)

    refresh_market_anchors(config, trade_date="20260604", tushare_call=lambda *_: _rows("dc_concept"))
    refresh_market_anchors(config, trade_date="20260604", tushare_call=lambda *_: [])

    assert list_market_anchors(config, trade_date="20260604") == []


def test_ensure_market_anchors_skips_existing_dictionary(tmp_path: Path):
    config = _config(tmp_path)
    calls = 0

    refresh_market_anchors(config, trade_date="20260604", tushare_call=lambda *_: _rows("dc_concept"))

    def fail_if_called(config, api_name, params, fields):
        nonlocal calls
        calls += 1
        raise AssertionError("不应请求 Tushare")

    result = ensure_market_anchors(
        config,
        trade_date="20260604",
        min_anchor_count=1,
        tushare_call=fail_if_called,
    )

    assert result.refreshed is False
    assert result.skipped_reason == "anchor 词库已存在"
    assert result.anchor_count == 1
    assert calls == 0


def test_ensure_market_anchors_uses_previous_open_trade_date(tmp_path: Path):
    config = _config(tmp_path)
    refresh_market_anchors(config, trade_date="20260605", tushare_call=lambda *_: _rows("dc_concept"))

    calls: list[str] = []

    def fake_call(config, api_name, params, fields):
        calls.append(api_name)
        if api_name == "trade_cal":
            return [
                {"cal_date": "20260605", "is_open": 1},
                {"cal_date": "20260606", "is_open": 0},
            ]
        raise AssertionError("不应刷新非交易日词库")

    result = ensure_market_anchors(
        config,
        trade_date="20260606",
        min_anchor_count=1,
        tushare_call=fake_call,
    )

    assert result.trade_date == "20260605"
    assert result.requested_trade_date == "20260606"
    assert result.refreshed is False
    assert result.anchor_count == 1
    assert result.skipped_reason == "20260606 非交易日，使用最近交易日 20260605 的 anchor 词库"
    assert calls == ["trade_cal"]


def test_ensure_market_anchors_keeps_open_trade_date(tmp_path: Path):
    config = _config(tmp_path)
    calls: list[str] = []

    def fake_call(config, api_name, params, fields):
        calls.append(api_name)
        if api_name == "trade_cal":
            return [{"cal_date": "20260608", "is_open": 1}]
        return _rows(api_name)

    result = ensure_market_anchors(
        config,
        trade_date="20260608",
        min_anchor_count=1,
        tushare_call=fake_call,
    )

    assert result.trade_date == "20260608"
    assert result.requested_trade_date == "20260608"
    assert result.refreshed is True
    assert result.anchor_count == 7
    assert calls == [
        "trade_cal",
        "dc_index",
        "dc_member",
        "kpl_list",
        "kpl_concept_cons",
        "tdx_index",
    ]


def test_ensure_market_anchors_falls_back_when_open_date_has_empty_dictionary(tmp_path: Path):
    config = _config(tmp_path)
    refresh_market_anchors(config, trade_date="20260605", tushare_call=lambda *_: _rows("dc_concept"))

    def fake_call(config, api_name, params, fields):
        if api_name == "trade_cal":
            return [
                {"cal_date": "20260605", "is_open": 1},
                {"cal_date": "20260608", "is_open": 1},
            ]
        return []

    result = ensure_market_anchors(
        config,
        trade_date="20260608",
        min_anchor_count=1,
        tushare_call=fake_call,
    )

    assert result.trade_date == "20260605"
    assert result.requested_trade_date == "20260608"
    assert result.refreshed is True
    assert result.anchor_count == 1
    assert result.skipped_reason == "20260608 anchor 词库不足，使用最近已有交易日 20260605 的 anchor 词库"


def test_ensure_market_anchors_retries_without_cache_before_fallback(monkeypatch, tmp_path: Path):
    config = _config(tmp_path)
    original_refresh = refresh_market_anchors
    refresh_cache_flags: list[bool] = []

    def fake_call(config, api_name, params, fields):
        if api_name == "trade_cal":
            return [{"cal_date": "20260608", "is_open": 1}]
        raise AssertionError("刷新由 fake_refresh 接管")

    def fake_refresh(config, *, trade_date, use_cache=True, tushare_call=None):
        refresh_cache_flags.append(use_cache)
        if use_cache:
            return original_refresh(config, trade_date=trade_date, tushare_call=lambda *_: [])
        return original_refresh(config, trade_date=trade_date, tushare_call=lambda *_: _rows("dc_concept"))

    monkeypatch.setattr("radar.core.market.anchors.refresh_market_anchors", fake_refresh)

    result = ensure_market_anchors(
        config,
        trade_date="20260608",
        min_anchor_count=1,
        tushare_call=fake_call,
    )

    assert result.trade_date == "20260608"
    assert result.anchor_count == 1
    assert result.refreshed is True
    assert refresh_cache_flags == [True, False]


def test_refresh_market_anchors_preserves_failed_source_rows(tmp_path: Path):
    config = _config(tmp_path)
    refresh_market_anchors(config, trade_date="20260604", tushare_call=lambda _config, api, _params, _fields: _rows(api))

    def fail_kpl(config, api_name, params, fields):
        if api_name == "kpl_list":
            raise RuntimeError("频率超限")
        return _rows(api_name)

    result = refresh_market_anchors(config, trade_date="20260604", tushare_call=fail_kpl)

    assert "kpl_concepts" in result.failed_sources
    conn = sqlite3.connect(tmp_path / "market.sqlite3")
    try:
        preserved = conn.execute(
            """
            SELECT COUNT(*) FROM market_anchors
            WHERE trade_date = '20260604' AND source IN ('kpl_list', 'kpl_concept_cons')
            """
        ).fetchone()[0]
    finally:
        conn.close()
    assert preserved == 3


def test_refresh_market_anchors_records_optional_source_failure(tmp_path: Path):
    def fake_call(config, api_name, params, fields):
        if api_name == "kpl_list":
            raise RuntimeError("频率超限")
        return _rows(api_name)

    result = refresh_market_anchors(
        _config(tmp_path),
        trade_date="20260604",
        tushare_call=fake_call,
    )

    assert result.anchor_count > 0
    assert "kpl_concepts" in result.failed_sources


def _rows(api_name: str) -> list[dict[str, Any]]:
    rows = {
        "dc_index": [
            {
                "ts_code": "000084.DC",
                "trade_date": "20260604",
                "name": "人形机器人",
                "leading": "国茂股份",
                "leading_code": "603915.SH",
            }
        ],
        "dc_member": [
            {
                "ts_code": "000084.DC",
                "con_code": "603915.SH",
                "trade_date": "20260604",
                "name": "国茂股份",
            },
            {
                "ts_code": "000084.DC",
                "con_code": "002164.SZ",
                "trade_date": "20260604",
                "name": "宁波东力",
            },
        ],
        "dc_concept": [
            {
                "theme_code": "000084.DC",
                "trade_date": "20260604",
                "name": "人形机器人",
                "hot": "910",
                "lead_stock": "国茂股份",
                "lead_stock_code": "603915.SH",
            }
        ],
        "dc_concept_cons": [
            {
                "ts_code": "603915.SH",
                "trade_date": "20260604",
                "name": "国茂股份",
                "theme_code": "000084.DC",
                "industry_code": "BK001",
                "industry": "电机",
                "reason": "减速器",
                "hot_num": "394",
            },
            {
                "ts_code": "002164.SZ",
                "trade_date": "20260604",
                "name": "宁波东力",
                "theme_code": "000084.DC",
                "industry_code": "BK001",
                "industry": "电机",
                "reason": "行星减速器",
                "hot_num": "639",
            },
        ],
        "kpl_list": [
            {
                "ts_code": "603915.SH",
                "name": "国茂股份",
                "trade_date": "20260604",
                "lu_desc": "机器人",
                "tag": "涨停",
                "theme": "机器人、减速器",
                "status": "首板",
            }
        ],
        "kpl_concept_cons": [
            {
                "ts_code": "000084.KP",
                "name": "机器人",
                "con_name": "国茂股份",
                "con_code": "603915.SH",
                "trade_date": "20260604",
                "desc": "精密减速器",
                "hot_num": 394,
            }
        ],
        "tdx_index": [
            {
                "ts_code": "880001.TDX",
                "trade_date": "20260604",
                "name": "通达信机器人",
                "idx_type": "概念板块",
            },
            {
                "ts_code": "880002.TDX",
                "trade_date": "20260604",
                "name": "算力",
                "idx_type": "概念板块",
            },
        ],
    }
    return rows.get(api_name, [])


def _config(tmp_path: Path) -> RadarConfig:
    return RadarConfig(
        storage={"data_dir": tmp_path},
        market={
            "provider": "tushare",
            "secret_ref": "tushare_main",
            "api_url": "https://example.invalid/tushare",
            "database": tmp_path / "market.sqlite3",
        },
        secrets=RadarSecrets(market={"tushare_main": {"token": "secret-token"}}),
    )
