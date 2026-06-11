from __future__ import annotations

import json
import uuid
from datetime import date, datetime, time
from pathlib import Path

from fastapi.testclient import TestClient

from radar.core.config import RadarConfig
from radar.core.db import migrate_market_db
from radar.core.store import connect, init_db
from radar.core.tushare import RealtimeDailyQuote
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


def test_stock_evidence_chain_latest_orders_by_actionable_priority(tmp_path: Path):
    config = _config(tmp_path)
    as_of = datetime(2026, 6, 9, 15, 0)
    window_start = datetime(2026, 6, 8, 15, 0)
    evidence_start = datetime(2026, 5, 1, 15, 0)
    conn = connect(config.database_path)
    try:
        init_db(conn)
        _insert_candidate(
            conn,
            as_of=as_of,
            window_start=window_start,
            evidence_start=evidence_start,
            ts_code="000001.SZ",
            stock_name="拥挤股份",
            rank=1,
            evidence_score=18,
            family_counts={"price": 6, "push": 3},
        )
        _insert_judgement(
            conn,
            as_of=as_of,
            window_start=window_start,
            evidence_start=evidence_start,
            ts_code="000001.SZ",
            stock_name="拥挤股份",
            stage="crowded",
            confidence=0.9,
            return_since_first_point=0.72,
        )
        _insert_candidate(
            conn,
            as_of=as_of,
            window_start=window_start,
            evidence_start=evidence_start,
            ts_code="000002.SZ",
            stock_name="早期股份",
            rank=2,
            evidence_score=12,
            family_counts={"catalyst": 2, "roadshow": 1},
        )
        _insert_judgement(
            conn,
            as_of=as_of,
            window_start=window_start,
            evidence_start=evidence_start,
            ts_code="000002.SZ",
            stock_name="早期股份",
            stage="seed",
            confidence=0.72,
            return_since_first_point=0.04,
        )
    finally:
        conn.close()

    client = TestClient(create_app(config))
    response = client.get("/api/strategy/evidence-chain/latest", params={"limit": 2})

    assert response.status_code == 200
    data = response.json()
    assert [item["stock_name"] for item in data["items"]] == ["早期股份", "拥挤股份"]
    assert data["items"][0]["rank"] == 2


def test_stock_evidence_chain_latest_includes_theme_recognition_context(tmp_path: Path):
    config = _config(tmp_path)
    as_of = datetime(2026, 6, 8, 15, 0)
    window_start = datetime(2026, 6, 5, 15, 0)
    evidence_start = datetime(2026, 5, 1, 15, 0)
    conn = connect(config.database_path)
    try:
        init_db(conn)
        _insert_candidate(
            conn,
            as_of=as_of,
            window_start=window_start,
            evidence_start=evidence_start,
            ts_code="300394.SZ",
            stock_name="天孚通信",
            rank=1,
            evidence_score=16,
            family_counts={"catalyst": 2, "research": 1},
        )
        _insert_judgement(
            conn,
            as_of=as_of,
            window_start=window_start,
            evidence_start=evidence_start,
            ts_code="300394.SZ",
            stock_name="天孚通信",
            stage="seed",
            confidence=0.78,
            return_since_first_point=0.13,
        )
    finally:
        conn.close()

    _insert_theme_context(config)
    daily = history.spec_for("daily")
    assert daily is not None
    history.put_rows(
        config.market_database_path,
        daily,
        [
            _daily("300394.SZ", "20260601", 10.0, 10.1, 9.9, 10.0, amount=10000),
            _daily("300394.SZ", "20260602", 10.0, 10.3, 9.9, 10.2, amount=10000),
            _daily("300394.SZ", "20260603", 10.2, 10.5, 10.1, 10.4, amount=10000),
            _daily("300394.SZ", "20260604", 10.4, 10.7, 10.3, 10.6, amount=10000),
            _daily("300394.SZ", "20260605", 10.6, 10.9, 10.5, 10.8, amount=10000),
            _daily("300394.SZ", "20260608", 10.8, 11.5, 10.7, 11.3, amount=30000),
            _daily("000001.SZ", "20260601", 10.0, 10.1, 9.9, 10.0, amount=10000),
            _daily("000001.SZ", "20260608", 10.0, 10.3, 9.9, 10.2, amount=12000),
        ],
    )

    client = TestClient(create_app(config))
    response = client.get("/api/strategy/evidence-chain/latest", params={"limit": 1})

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["primary_theme"]["theme_name"] == "CPO概念"
    assert item["themes"][0]["return_rank_5d"] == 1
    assert item["themes"][0]["member_count"] == 2
    assert item["recognition"]["state"] == "confirmed"
    assert "CPO概念" in item["recognition"]["reasons"][0]


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


def test_strategy_stock_chart_endpoint_appends_intraday_realtime_candle(monkeypatch, tmp_path: Path):
    config = _config(tmp_path)
    daily = history.spec_for("daily")
    assert daily is not None
    history.put_rows(
        config.market_database_path,
        daily,
        [_daily("300503.SZ", "20260605", 80.0, 82.0, 78.0, 81.0, pct_chg=1.25)],
    )
    monkeypatch.setattr("radar.core.usecases.stock_evidence_chain.stock_chart._refresh_recent_daily_cache", lambda *args, **kwargs: None)
    monkeypatch.setattr("radar.core.tushare.history._today_date", lambda: date(2026, 6, 8))
    monkeypatch.setattr("radar.core.usecases.stock_evidence_chain.stock_chart._now_time", lambda: time(10, 30))
    monkeypatch.setattr("radar.core.usecases.stock_evidence_chain.stock_chart._is_trading_day", lambda *args, **kwargs: True)

    def fake_quote(config_arg, *, ts_code, use_cache):
        assert ts_code == "300503.SZ"
        assert use_cache is True
        return RealtimeDailyQuote(
            ts_code=ts_code,
            name="昊志机电",
            pre_close=81.0,
            open=83.0,
            high=88.0,
            low=82.5,
            close=86.0,
            vol=2000,
            amount=30000,
            num=120,
        )

    monkeypatch.setattr("radar.core.usecases.stock_evidence_chain.stock_chart.get_realtime_daily_quote", fake_quote)

    client = TestClient(create_app(config))
    response = client.get("/api/strategy/stocks/300503.SZ/chart", params={"days": 5})

    assert response.status_code == 200
    data = response.json()
    assert data["latest_trade_date"] == "20260608"
    assert data["latest_source"] == "rt_k"
    assert data["latest_is_realtime"] is True
    assert [item["trade_date"] for item in data["candles"]] == ["20260605", "20260608"]
    assert data["candles"][-1]["close"] == 86.0
    assert data["candles"][-1]["amount"] == 30000


def _config(tmp_path: Path) -> RadarConfig:
    return RadarConfig(storage={"data_dir": tmp_path / "data", "database": tmp_path / "radar.sqlite3"})


def _insert_theme_context(config: RadarConfig) -> None:
    conn = connect(config.market_database_path)
    try:
        migrate_market_db(conn)
        now = "2026-06-08T15:00:00"
        conn.execute(
            """
            INSERT INTO theme_nodes (
                theme_id, theme_name, theme_type, parent_theme_id, aliases_json,
                policy_tags_json, status, created_at, updated_at
            ) VALUES (?, ?, ?, NULL, ?, '[]', 'active', ?, ?)
            """,
            ("theme:auto:cpo", "CPO概念", "concept", json.dumps(["CPO概念"], ensure_ascii=False), now, now),
        )
        rows = [
            ("theme:auto:cpo", "300394.SZ", "天孚通信"),
            ("theme:auto:cpo", "000001.SZ", "平安银行"),
        ]
        conn.executemany(
            """
            INSERT INTO stock_theme_memberships (
                theme_id, ts_code, stock_name, role, confidence, source_count,
                sources_json, reasons_json, first_seen_date, last_seen_date,
                latest_trade_date, updated_at
            ) VALUES (?, ?, ?, 'elastic', 0.82, 2, '[]', ?, '20260601', '20260608', '20260608', ?)
            """,
            [(theme_id, ts_code, name, json.dumps(["多源主题归属"], ensure_ascii=False), now) for theme_id, ts_code, name in rows],
        )
        conn.commit()
    finally:
        conn.close()


def _daily(
    ts_code: str,
    trade_date: str,
    open_price: float,
    high: float,
    low: float,
    close: float,
    *,
    pct_chg: float | None = None,
    amount: float = 10000,
):
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
        "amount": amount,
    }


def _insert_candidate(
    conn,
    *,
    as_of: datetime,
    window_start: datetime,
    evidence_start: datetime,
    ts_code: str,
    stock_name: str,
    rank: int,
    evidence_score: int,
    family_counts: dict[str, int],
) -> None:
    conn.execute(
        """
        INSERT INTO stock_lifecycle_candidates (
            as_of_time, window_start_time, evidence_start_time, ts_code, stock_name,
            trigger_count, unique_trigger_count, sender_count, conversation_count,
            evidence_score, channels_json, family_counts_json, rank, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            as_of.isoformat(),
            window_start.isoformat(),
            evidence_start.isoformat(),
            ts_code,
            stock_name,
            12,
            8,
            4,
            4,
            evidence_score,
            json.dumps(["heat"], ensure_ascii=False),
            json.dumps(family_counts, ensure_ascii=False),
            rank,
            as_of.isoformat(),
        ),
    )
    conn.commit()


def _insert_judgement(
    conn,
    *,
    as_of: datetime,
    window_start: datetime,
    evidence_start: datetime,
    ts_code: str,
    stock_name: str,
    stage: str,
    confidence: float,
    return_since_first_point: float,
) -> None:
    result = {
        "stage_label": {"seed": "种子期", "crowded": "拥挤期"}[stage],
        "one_line": f"{stock_name} 测试判断",
        "why": ["测试证据"],
        "market_evidence": {
            "summary": {
                "return_since_first_point": return_since_first_point,
                "drawdown_from_selected_high": -0.02,
            },
            "points": [],
        },
    }
    conn.execute(
        """
        INSERT INTO stock_lifecycle_judgements (
            judgement_id, as_of_time, window_start_time, evidence_start_time, ts_code,
            stock_name, stage, confidence, trigger_count, unique_trigger_count,
            sender_count, conversation_count, evidence_count, channels_json,
            evidence_refs_json, llm_provider, model, prompt_version,
            result_json, created_at, updated_at, evidence_signature
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            uuid.uuid4().hex,
            as_of.isoformat(),
            window_start.isoformat(),
            evidence_start.isoformat(),
            ts_code,
            stock_name,
            stage,
            confidence,
            12,
            8,
            4,
            4,
            6,
            json.dumps(["heat"], ensure_ascii=False),
            "[]",
            "test",
            "test",
            "test",
            json.dumps(result, ensure_ascii=False),
            as_of.isoformat(),
            as_of.isoformat(),
            "test",
        ),
    )
    conn.commit()
