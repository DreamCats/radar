from __future__ import annotations

from contextlib import closing
from types import SimpleNamespace

from fastapi.testclient import TestClient

from radar.core.config import RadarConfig
from radar.core.storage import connect, migrate_message_db, start_run
from radar.web.server.app import create_app
from radar.web.server.schemas import DerivedJobItem


def test_schedules_endpoint_seeds_defaults(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    response = client.get("/api/schedules")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["schedule_id"] for item in items] == [
        "wechat-ingest-incremental",
        "market-stock-refresh-morning",
        "analyst-backtest-close",
        "catalyst-strategy-hourly",
    ]
    assert items[0]["window_preset"] == "yesterday_1500_to_now"
    assert _find(items, "wechat-ingest-incremental")["enabled"] is False
    assert _find(items, "analyst-backtest-close")["enabled"] is False
    market_schedule = _find(items, "market-stock-refresh-morning")
    assert market_schedule["enabled"] is True
    assert market_schedule["cadence"] == {"time": "08:30", "weekdays_only": False}
    catalyst_schedule = _find(items, "catalyst-strategy-hourly")
    assert catalyst_schedule["enabled"] is False
    assert catalyst_schedule["window_preset"] == "last_1h"
    assert catalyst_schedule["cadence"] == {
        "minutes": 60,
        "offset_minutes": 0,
        "active_start": "08:00",
        "active_end": "22:00",
    }
    assert catalyst_schedule["request"]["publish"] is True
    assert catalyst_schedule["request"]["notify"] is True


def test_schedules_endpoint_syncs_existing_catalyst_default(tmp_path):
    config = _config(tmp_path)
    current = "2026-06-28T20:00:00"
    with closing(connect(config.database_path)) as conn:
        migrate_message_db(conn)
        conn.execute(
            """
            INSERT INTO job_schedules (
                schedule_id, job_key, title, enabled, timezone, cadence_kind,
                cadence_json, window_preset, request_json, catch_up_policy,
                max_lag_minutes, next_tick_at, sort_order, created_at, updated_at
            ) VALUES (
                'catalyst-strategy-hourly', 'catalyst_strategy', '催化策略报告', 1,
                'Asia/Shanghai', 'interval',
                '{"active_end":"22:00","active_start":"08:00","minutes":60,"offset_minutes":0}',
                'last_1h',
                '{"limit":200,"llm_concurrency":3,"max_stocks":12,"notify":false,"publish":true}',
                'latest_only', 60, ?, 30, ?, ?
            )
            """,
            (current, current, current),
        )
        conn.commit()

    response = TestClient(create_app(config)).get("/api/schedules")

    assert response.status_code == 200
    catalyst_schedule = _find(response.json()["items"], "catalyst-strategy-hourly")
    assert catalyst_schedule["enabled"] is False
    assert catalyst_schedule["request"]["notify"] is True


def test_schedules_endpoint_removes_retired_defaults(tmp_path):
    config = _config(tmp_path)
    current = "2026-06-23T10:00:00"
    with closing(connect(config.database_path)) as conn:
        migrate_message_db(conn)
        conn.execute(
            """
            INSERT INTO job_schedules (
                schedule_id, job_key, title, enabled, timezone, cadence_kind,
                cadence_json, window_preset, request_json, catch_up_policy,
                max_lag_minutes, next_tick_at, sort_order, created_at, updated_at
            ) VALUES (?, ?, ?, 0, 'Asia/Shanghai', 'interval', ?, NULL, '{}',
                'latest_only', 60, ?, 20, ?, ?)
            """,
            (
                "message-classify-incremental",
                "message_classify",
                "消息分类增量",
                '{"minutes": 30}',
                current,
                current,
                current,
            ),
        )
        conn.execute(
            """
            INSERT INTO job_schedules (
                schedule_id, job_key, title, enabled, timezone, cadence_kind,
                cadence_json, window_preset, request_json, catch_up_policy,
                max_lag_minutes, next_tick_at, sort_order, created_at, updated_at
            ) VALUES (?, ?, ?, 0, 'Asia/Shanghai', 'daily', ?, NULL, '{}',
                'latest_only', 60, ?, 30, ?, ?)
            """,
            (
                "market-anchor-close",
                "market_anchor_update",
                "Anchor 更新",
                '{"time": "15:20"}',
                current,
                current,
                current,
            ),
        )
        conn.execute(
            """
            INSERT INTO job_schedule_ticks (
                tick_id, schedule_id, planned_at, status, run_ids_json,
                request_json, created_at, updated_at
            ) VALUES (?, ?, ?, 'running', '[]', '{}', ?, ?)
            """,
            ("tick-retired", "message-classify-incremental", current, current, current),
        )
        conn.commit()

    response = TestClient(create_app(config)).get("/api/schedules")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["schedule_id"] for item in items] == [
        "wechat-ingest-incremental",
        "market-stock-refresh-morning",
        "analyst-backtest-close",
        "catalyst-strategy-hourly",
    ]
    with closing(connect(config.database_path)) as conn:
        schedules_count = conn.execute(
            """
            SELECT COUNT(*) FROM job_schedules
            WHERE schedule_id IN ('message-classify-incremental', 'market-anchor-close')
               OR job_key IN ('message_classify', 'market_anchor_update')
            """
        ).fetchone()[0]
        ticks_count = conn.execute(
            """
            SELECT COUNT(*) FROM job_schedule_ticks
            WHERE schedule_id IN ('message-classify-incremental', 'market-anchor-close')
            """
        ).fetchone()[0]
    assert schedules_count == 0
    assert ticks_count == 0


def test_schedule_enable_disable(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    enabled = client.post("/api/schedules/wechat-ingest-incremental/enable")
    disabled = client.post("/api/schedules/wechat-ingest-incremental/disable")

    assert enabled.status_code == 200
    assert _find(enabled.json()["items"], "wechat-ingest-incremental")["enabled"] is True
    assert disabled.status_code == 200
    assert _find(disabled.json()["items"], "wechat-ingest-incremental")["enabled"] is False


def test_schedule_run_now_submits_existing_job(monkeypatch, tmp_path):
    config = _config(tmp_path)
    captured: dict[str, object] = {}

    def fake_submit(config, request):
        captured["source"] = request.source
        captured["force"] = request.force
        captured["start_time"] = request.start_time
        captured["end_time"] = request.end_time
        return [
            SimpleNamespace(run_id="run-personal", reused_existing=False),
            SimpleNamespace(run_id="run-group", reused_existing=False),
        ]

    monkeypatch.setattr("radar.web.server.schedule_jobs.submit_wechat_ingest_jobs", fake_submit)

    client = TestClient(create_app(config))
    response = client.post("/api/schedules/wechat-ingest-incremental/run-now")

    assert response.status_code == 200
    item = response.json()["item"]
    assert item["status"] == "submitted"
    assert item["run_ids"] == ["run-personal", "run-group"]
    assert captured["source"] == "all"
    assert captured["force"] is False
    assert captured["start_time"].hour == 15
    assert captured["end_time"] > captured["start_time"]


def test_schedule_run_now_submits_market_stock_refresh(monkeypatch, tmp_path):
    config = _config(tmp_path)
    captured: dict[str, object] = {}

    def fake_submit(config, request):
        captured["force"] = request.force
        return SimpleNamespace(run_id="run-market-stocks", reused_existing=False)

    monkeypatch.setattr("radar.web.server.schedule_jobs.submit_market_stock_refresh_job", fake_submit)

    client = TestClient(create_app(config))
    response = client.post("/api/schedules/market-stock-refresh-morning/run-now")

    assert response.status_code == 200
    item = response.json()["item"]
    assert item["status"] == "submitted"
    assert item["run_ids"] == ["run-market-stocks"]
    assert item["request"] == {"force": True}
    assert captured["force"] is True


def test_schedule_run_now_submits_catalyst_strategy(monkeypatch, tmp_path):
    config = _config(tmp_path)
    captured: dict[str, object] = {}

    def fake_submit(config, request):
        captured["publish"] = request.publish
        captured["notify"] = request.notify
        captured["start_time"] = request.start_time
        captured["end_time"] = request.end_time
        return SimpleNamespace(run_id="run-catalyst", reused_existing=False)

    monkeypatch.setattr("radar.web.server.schedule_jobs.submit_catalyst_strategy_job", fake_submit)

    client = TestClient(create_app(config))
    response = client.post("/api/schedules/catalyst-strategy-hourly/run-now")

    assert response.status_code == 200
    item = response.json()["item"]
    assert item["status"] == "submitted"
    assert item["run_ids"] == ["run-catalyst"]
    assert item["request"]["publish"] is True
    assert item["request"]["notify"] is True
    assert captured["publish"] is True
    assert captured["notify"] is True
    assert captured["end_time"] > captured["start_time"]


def test_catalyst_strategy_job_endpoint_submits(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def fake_submit(config, request):
        captured["publish"] = request.publish
        captured["notify"] = request.notify
        return DerivedJobItem(
            job_type="catalyst_strategy",
            run_id="run-catalyst-manual",
            reused_existing=False,
            status="running",
        )

    monkeypatch.setattr("radar.web.server.routers.catalyst_strategy.submit_catalyst_strategy_job", fake_submit)

    response = TestClient(create_app(_config(tmp_path))).post(
        "/api/catalyst-strategy/jobs",
        json={
            "start_time": "2026-06-28T19:00:00",
            "end_time": "2026-06-28T20:00:00",
            "limit": 200,
            "max_stocks": 12,
            "llm_concurrency": 3,
            "publish": True,
            "notify": True,
        },
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["job_type"] == "catalyst_strategy"
    assert item["run_id"] == "run-catalyst-manual"
    assert captured == {"publish": True, "notify": True}


def test_schedule_run_now_skips_when_same_job_running(monkeypatch, tmp_path):
    config = _config(tmp_path)
    start_run(config.database_path, kind="wechat_ingest_range", target="personal_message:running")

    def fake_submit(config, request):
        raise AssertionError("running schedule should skip submit")

    monkeypatch.setattr("radar.web.server.schedule_jobs.submit_wechat_ingest_jobs", fake_submit)

    client = TestClient(create_app(config))
    response = client.post("/api/schedules/wechat-ingest-incremental/run-now")

    assert response.status_code == 200
    item = response.json()["item"]
    assert item["status"] == "skipped"
    assert item["skipped_reason"] == "previous_tick_running"


def _config(tmp_path) -> RadarConfig:
    return RadarConfig(
        storage={
            "data_dir": tmp_path / "data",
            "database": tmp_path / "radar.sqlite3",
        },
        scheduler={"enabled": False},
    )


def _find(items: list[dict], schedule_id: str) -> dict:
    return next(item for item in items if item["schedule_id"] == schedule_id)
