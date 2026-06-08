from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from threading import Event

from fastapi.testclient import TestClient

from radar.core.config import RadarConfig
from radar.core.models import MessageAnchor, MessageClassification, RawMessage
from radar.core.runs import get_run
from radar.core.store import connect, init_db, replace_message_anchors, upsert_message_classifications, upsert_messages
from radar.core.tushare import history
from radar.core.usecases.strategy import LeadSignalSummary
from radar.core.usecases.strategy.snapshots import StrategySnapshotBackfillResult, StrategySnapshotSaveResult
from radar.web.server.app import create_app


def test_strategy_opportunities_endpoint_returns_ranked_items(tmp_path: Path):
    config = _config(tmp_path)
    messages = [
        _message("m1", "2026-06-07T10:00:00", "PCB 订单 扩产"),
        _message("m2", "2026-06-06T10:00:00", "PCB 业绩 放量"),
        _message("m3", "2026-06-05T10:00:00", "PCB 涨价"),
    ]
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, messages)
        upsert_message_classifications(conn, [_classification(message) for message in messages])
        replace_message_anchors(
            conn,
            message_ids=[message.message_id for message in messages],
            anchors=[_anchor(message, "PCB") for message in messages],
            trade_date="20260607",
            extractor_version="test-anchor",
        )
    finally:
        conn.close()

    client = TestClient(create_app(config))
    response = client.get("/api/strategy/opportunities", params={"days": 30, "recent_days": 7, "limit": 3})

    assert response.status_code == 200
    data = response.json()
    assert data["opportunities"][0]["name"] == "PCB"
    assert data["opportunities"][0]["recent_message_count"] == 3
    assert data["opportunities"][0]["opportunity_backtest"]["event_count"] == 0
    assert data["opportunities"][0]["selected_stock_backtest"]["event_count"] == 0


def test_strategy_validation_endpoint_returns_empty_summary(tmp_path: Path):
    client = TestClient(create_app(_config(tmp_path)))
    response = client.get("/api/strategy/validation", params={"window_days": 5})

    assert response.status_code == 200
    data = response.json()
    assert data["window_days"] == 5
    assert data["snapshot_count"] == 0
    assert data["matured_stock_count"] == 0
    assert data["by_decision_bucket"] == []


def test_strategy_stock_chart_endpoint_reads_local_market_history(monkeypatch, tmp_path: Path):
    config = _config(tmp_path)
    monkeypatch.setattr("radar.core.usecases.strategy.stock_chart._refresh_recent_daily_cache", lambda *args, **kwargs: None)
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
    monkeypatch.setattr("radar.core.usecases.strategy.stock_chart._refresh_recent_daily_cache", lambda *args, **kwargs: None)
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

    monkeypatch.setattr("radar.core.usecases.strategy.stock_chart.tushare_client.call", fake_call)

    client = TestClient(create_app(config))
    response = client.get("/api/strategy/stocks/300024.SZ/chart", params={"days": 5})

    assert response.status_code == 200
    data = response.json()
    assert calls == [{"ts_code": "300024.SZ", "start_date": "20260606", "end_date": "20260608"}]
    assert data["latest_trade_date"] == "20260608"
    assert [item["trade_date"] for item in data["candles"]] == ["20260605", "20260608"]


def test_lead_signals_endpoint_returns_summary(monkeypatch, tmp_path: Path):
    config = _config(tmp_path)
    calls: list[dict] = []

    def fake_summary(
        config,
        *,
        as_of_date,
        days,
        limit,
        source_limit,
        benchmark_ts_code,
        message_day_max_pct,
        strong_return_pct,
        limit_like_pct,
    ):
        calls.append(
            {
                "as_of_date": as_of_date,
                "days": days,
                "limit": limit,
                "source_limit": source_limit,
                "benchmark_ts_code": benchmark_ts_code,
                "message_day_max_pct": message_day_max_pct,
                "strong_return_pct": strong_return_pct,
                "limit_like_pct": limit_like_pct,
            }
        )
        now = datetime.fromisoformat("2026-06-07T12:00:00")
        return LeadSignalSummary(
            start_time=now,
            end_time=now,
            generated_at=now,
            as_of_date=as_of_date or "2026-06-07",
            validation_days=days,
            benchmark_ts_code=benchmark_ts_code,
            message_day_max_pct=message_day_max_pct,
            strong_return_pct=strong_return_pct,
            limit_like_pct=limit_like_pct,
            event_count=3,
            stock_day_count=2,
            pre_rise_stock_day_count=1,
        )

    monkeypatch.setattr("radar.web.server.routers.strategy.summarize_lead_signals", fake_summary)

    client = TestClient(create_app(config))
    response = client.get(
        "/api/strategy/lead-signals",
        params={"as_of_date": "2026-06-06", "days": 20, "limit": 5, "source_limit": 3, "message_day_max_pct": 1.5},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["event_count"] == 3
    assert data["pre_rise_stock_day_count"] == 1
    assert calls == [
        {
            "as_of_date": "2026-06-06",
            "days": 20,
            "limit": 5,
            "source_limit": 3,
            "benchmark_ts_code": "000300.SH",
            "message_day_max_pct": 1.5,
            "strong_return_pct": 3.0,
            "limit_like_pct": 9.5,
        }
    ]


def test_strategy_snapshot_save_endpoint_uses_cache(monkeypatch, tmp_path: Path):
    config = _config(tmp_path)
    calls: list[dict] = []

    def fake_save(config, *, days, recent_days, limit, force):
        calls.append({"days": days, "recent_days": recent_days, "limit": limit, "force": force})
        return StrategySnapshotSaveResult(
            snapshot_id="snap-1",
            generated_at=datetime.fromisoformat("2026-06-07T12:00:00"),
            stock_count=2,
            opportunity_count=3,
            reused_existing=True,
        )

    monkeypatch.setattr("radar.web.server.routers.strategy.save_cached_strategy_snapshot", fake_save)

    client = TestClient(create_app(config))
    response = client.post(
        "/api/strategy/snapshots",
        json={"days": 30, "recent_days": 7, "limit": 12, "force": False},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["snapshot_id"] == "snap-1"
    assert data["reused_existing"] is True
    assert calls == [{"days": 30, "recent_days": 7, "limit": 12, "force": False}]


def test_strategy_backfill_jobs_endpoint_starts_and_reuses_running_job(monkeypatch, tmp_path: Path):
    config = _config(tmp_path)
    calls: list[dict] = []
    started = Event()
    finished = Event()
    release = Event()

    def fake_backfill(config, *, windows, benchmark_ts_code, snapshot_start_time, snapshot_end_time):
        try:
            started.set()
            release.wait(timeout=2)
            calls.append(
                {
                    "windows": windows,
                    "benchmark_ts_code": benchmark_ts_code,
                    "snapshot_start_time": snapshot_start_time,
                    "snapshot_end_time": snapshot_end_time,
                }
            )
            return StrategySnapshotBackfillResult(
                snapshot_count=1,
                stock_count=2,
                refreshed_count=1,
                pending_count=1,
                missing_price_count=0,
                failed_count=0,
                windows=windows,
            )
        finally:
            finished.set()

    monkeypatch.setattr("radar.web.server.strategy_jobs.backfill_strategy_snapshot_returns", fake_backfill)

    client = TestClient(create_app(config))
    payload = {
        "start_time": "2026-05-08T00:00:00",
        "end_time": "2026-06-07T00:00:00",
        "windows": [1, 3, 5, 10],
        "benchmark_ts_code": "000300.SH",
    }
    response = client.post("/api/strategy/snapshots/backfill/jobs", json=payload)

    assert response.status_code == 200
    first = response.json()["items"][0]
    assert first["job_type"] == "strategy_backfill"
    assert first["status"] == "running"
    assert first["reused_existing"] is False
    assert started.wait(timeout=1)
    assert get_run(config.database_path, first["run_id"]) is not None

    response = client.post("/api/strategy/snapshots/backfill/jobs", json=payload)
    second = response.json()["items"][0]

    assert second["run_id"] == first["run_id"]
    assert second["reused_existing"] is True
    release.set()
    assert finished.wait(timeout=1)
    assert calls[0]["snapshot_start_time"] == datetime.fromisoformat("2026-05-08T00:00:00")
    assert calls[0]["snapshot_end_time"] == datetime.fromisoformat("2026-06-07T00:00:00")


def _config(tmp_path: Path) -> RadarConfig:
    return RadarConfig(storage={"data_dir": tmp_path / "data", "database": tmp_path / "radar.sqlite3"})


def _message(message_id: str, message_time: str, content: str) -> RawMessage:
    return RawMessage(
        message_id=message_id,
        source="个人群",
        sender=f"sender-{message_id}",
        message_time=datetime.fromisoformat(message_time),
        raw_content=content,
        group_name="策略测试群",
        fetch_time=datetime.fromisoformat("2026-06-07T10:01:00"),
        fetch_window="20260607100000-20260607110000",
    )


def _classification(message: RawMessage) -> MessageClassification:
    now = datetime.fromisoformat("2026-06-07T12:00:00")
    return MessageClassification(
        message_id=message.message_id,
        category="recommendation",
        confidence=0.9,
        reason="策略测试",
        status="auto",
        classifier_type="llm",
        classifier_version="test",
        created_at=now,
        updated_at=now,
    )


def _anchor(message: RawMessage, name: str) -> MessageAnchor:
    now = datetime.fromisoformat("2026-06-07T12:00:00")
    return MessageAnchor(
        message_id=message.message_id,
        anchor_id=f"concept:{name}",
        anchor_type="concept",
        name=name,
        confidence=0.9,
        evidence=[],
        extractor_version="test-anchor",
        trade_date="20260607",
        created_at=now,
        updated_at=now,
    )


def _daily(
    ts_code: str,
    trade_date: str,
    open_: float,
    high: float,
    low: float,
    close: float,
    *,
    pct_chg: float,
) -> dict:
    return {
        "ts_code": ts_code,
        "trade_date": trade_date,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "pre_close": open_,
        "change": close - open_,
        "pct_chg": pct_chg,
        "vol": 10000,
        "amount": 120000,
    }
