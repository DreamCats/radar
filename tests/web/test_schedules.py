from __future__ import annotations

from contextlib import closing
from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from radar.core.config import RadarConfig
from radar.core.storage import connect, get_run, migrate, migrate_message_db, start_run
from radar.core.storage.message_migrations import MESSAGE_MIGRATIONS
from radar.core.storage.report_store import get_catalyst_valuation_report, save_catalyst_valuation_report
from radar.core.usecases.catalyst_valuation_report.models import (
    CatalystValuationEvidence,
    CatalystValuationReport,
    CatalystValuationReportRunResult,
    CatalystValuationStockContext,
)
from radar.web.server.app import create_app
from radar.web.server.catalyst_valuation_report_jobs import (
    CATALYST_VALUATION_REPORT_RUN_KIND,
    _run_catalyst_valuation_report_job,
)
from radar.web.server.schemas import CatalystValuationReportJobRequest, DerivedJobItem


def test_schedules_endpoint_seeds_defaults(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    response = client.get("/api/schedules")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["schedule_id"] for item in items] == [
        "wechat-ingest-incremental",
        "market-stock-refresh-morning",
        "analyst-backtest-close",
        "catalyst-valuation-report-hourly",
    ]
    assert items[0]["window_preset"] == "yesterday_1500_to_now"
    assert _find(items, "wechat-ingest-incremental")["enabled"] is False
    assert _find(items, "analyst-backtest-close")["enabled"] is False
    market_schedule = _find(items, "market-stock-refresh-morning")
    assert market_schedule["enabled"] is True
    assert market_schedule["cadence"] == {"time": "08:30", "weekdays_only": False}
    catalyst_schedule = _find(items, "catalyst-valuation-report-hourly")
    assert catalyst_schedule["enabled"] is False
    assert catalyst_schedule["window_preset"] == "last_1h"
    assert catalyst_schedule["cadence"] == {
        "minutes": 60,
        "offset_minutes": 0,
        "active_start": "08:00",
        "active_end": "23:00",
    }
    assert catalyst_schedule["request"]["publish"] is True
    assert catalyst_schedule["request"]["notify"] is True
    assert catalyst_schedule["request"]["auto_upside"] is True
    assert catalyst_schedule["request"]["max_stocks"] == 20
    assert "llm_concurrency" not in catalyst_schedule["request"]


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
                'catalyst-valuation-report-hourly', 'catalyst_valuation_report', '催化估值线索报告', 1,
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
    catalyst_schedule = _find(response.json()["items"], "catalyst-valuation-report-hourly")
    assert catalyst_schedule["enabled"] is False
    assert catalyst_schedule["cadence"] == {
        "active_end": "23:00",
        "active_start": "08:00",
        "minutes": 60,
        "offset_minutes": 0,
    }
    assert catalyst_schedule["request"]["notify"] is True
    assert catalyst_schedule["request"]["auto_upside"] is True
    assert catalyst_schedule["request"]["max_stocks"] == 12
    assert "llm_concurrency" not in catalyst_schedule["request"]


def test_message_migration_renames_catalyst_valuation_report_identifiers(tmp_path):
    config = _config(tmp_path)
    current = "2026-06-28T20:00:00"
    with closing(connect(config.database_path)) as conn:
        migrate(conn, MESSAGE_MIGRATIONS[:1])
        conn.execute(
            """
            INSERT INTO job_schedules (
                schedule_id, job_key, title, enabled, timezone, cadence_kind,
                cadence_json, window_preset, request_json, catch_up_policy,
                max_lag_minutes, next_tick_at, sort_order, created_at, updated_at
            ) VALUES (
                'catalyst-strategy-hourly', 'catalyst_strategy', '旧催化策略', 1,
                'Asia/Shanghai', 'interval',
                '{"active_end":"22:00","active_start":"08:00","minutes":60,"offset_minutes":0}',
                'last_1h',
                '{"limit":200,"llm_concurrency":3,"max_stocks":12,"notify":true,"publish":true}',
                'latest_only', 60, ?, 30, ?, ?
            )
            """,
            (current, current, current),
        )
        conn.execute(
            """
            INSERT INTO job_schedule_ticks (
                tick_id, schedule_id, planned_at, status, run_ids_json,
                request_json, created_at, updated_at
            ) VALUES (
                'tick-catalyst', 'catalyst-strategy-hourly', ?, 'succeeded', '["run-catalyst"]',
                '{"limit":200,"llm_concurrency":3,"max_stocks":12}', ?, ?
            )
            """,
            (current, current, current),
        )
        conn.execute(
            """
            INSERT INTO runs (
                run_id, kind, target, started_at, finished_at, status,
                raw_count, stored_count, filtered_count, metadata_json
            ) VALUES (
                'run-catalyst', 'catalyst_strategy_report', 'manual', ?, ?, 'succeeded',
                1, 1, 0, '{"job_key":"catalyst_strategy","run_kind":"catalyst_strategy_report"}'
            )
            """,
            (current, current),
        )
        conn.commit()

        migrate_message_db(conn)

        schedule = conn.execute("SELECT * FROM job_schedules").fetchone()
        tick = conn.execute("SELECT * FROM job_schedule_ticks").fetchone()
        run = conn.execute("SELECT * FROM runs").fetchone()

    assert schedule["schedule_id"] == "catalyst-valuation-report-hourly"
    assert schedule["job_key"] == "catalyst_valuation_report"
    assert "llm_concurrency" not in schedule["request_json"]
    assert '"max_stocks":12' in schedule["request_json"]
    assert tick["schedule_id"] == "catalyst-valuation-report-hourly"
    assert "llm_concurrency" not in tick["request_json"]
    assert run["kind"] == "catalyst_valuation_report"
    assert "catalyst_strategy" not in run["metadata_json"]


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
            INSERT INTO job_schedules (
                schedule_id, job_key, title, enabled, timezone, cadence_kind,
                cadence_json, window_preset, request_json, catch_up_policy,
                max_lag_minutes, next_tick_at, sort_order, created_at, updated_at
            ) VALUES (?, ?, ?, 0, 'Asia/Shanghai', 'interval', ?, 'last_1h', ?,
                'latest_only', 60, ?, 30, ?, ?)
            """,
            (
                "catalyst-strategy-hourly",
                "catalyst_strategy",
                "催化策略报告",
                '{"minutes": 60}',
                '{"limit":200,"llm_concurrency":3,"max_stocks":12,"notify":true,"publish":true}',
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
        conn.execute(
            """
            INSERT INTO job_schedule_ticks (
                tick_id, schedule_id, planned_at, status, run_ids_json,
                request_json, created_at, updated_at
            ) VALUES (?, ?, ?, 'running', '[]', '{}', ?, ?)
            """,
            ("tick-old-catalyst", "catalyst-strategy-hourly", current, current, current),
        )
        conn.commit()

    response = TestClient(create_app(config)).get("/api/schedules")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["schedule_id"] for item in items] == [
        "wechat-ingest-incremental",
        "market-stock-refresh-morning",
        "analyst-backtest-close",
        "catalyst-valuation-report-hourly",
    ]
    with closing(connect(config.database_path)) as conn:
        schedules_count = conn.execute(
            """
            SELECT COUNT(*) FROM job_schedules
            WHERE schedule_id IN (
                'message-classify-incremental',
                'market-anchor-close',
                'catalyst-strategy-hourly'
            )
               OR job_key IN ('message_classify', 'market_anchor_update', 'catalyst_strategy')
            """
        ).fetchone()[0]
        ticks_count = conn.execute(
            """
            SELECT COUNT(*) FROM job_schedule_ticks
            WHERE schedule_id IN (
                'message-classify-incremental',
                'market-anchor-close',
                'catalyst-strategy-hourly'
            )
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


def test_schedule_request_update_persists_catalyst_switches(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    response = client.patch(
        "/api/schedules/catalyst-valuation-report-hourly/request",
        json={
            "request": {
                "limit": 200,
                "max_stocks": 20,
                "publish": True,
                "notify": False,
                "auto_upside": False,
            }
        },
    )

    assert response.status_code == 200
    schedule = _find(response.json()["items"], "catalyst-valuation-report-hourly")
    assert schedule["request"]["publish"] is True
    assert schedule["request"]["notify"] is False
    assert schedule["request"]["auto_upside"] is False


def test_schedule_request_update_enables_publish_for_notify(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    response = client.patch(
        "/api/schedules/catalyst-valuation-report-hourly/request",
        json={"request": {"limit": 200, "publish": False, "notify": True, "auto_upside": True}},
    )

    assert response.status_code == 200
    schedule = _find(response.json()["items"], "catalyst-valuation-report-hourly")
    assert schedule["request"]["publish"] is True
    assert schedule["request"]["notify"] is True


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


def test_schedule_run_now_submits_catalyst_valuation_report(monkeypatch, tmp_path):
    config = _config(tmp_path)
    captured: dict[str, object] = {}

    def fake_submit(config, request):
        captured["publish"] = request.publish
        captured["notify"] = request.notify
        captured["auto_upside"] = request.auto_upside
        captured["max_stocks"] = request.max_stocks
        captured["start_time"] = request.start_time
        captured["end_time"] = request.end_time
        return SimpleNamespace(run_id="run-catalyst", reused_existing=False)

    monkeypatch.setattr("radar.web.server.schedule_jobs.submit_catalyst_valuation_report_job", fake_submit)

    client = TestClient(create_app(config))
    response = client.post("/api/schedules/catalyst-valuation-report-hourly/run-now")

    assert response.status_code == 200
    item = response.json()["item"]
    assert item["status"] == "submitted"
    assert item["run_ids"] == ["run-catalyst"]
    assert item["request"]["publish"] is True
    assert item["request"]["notify"] is True
    assert item["request"]["auto_upside"] is True
    assert item["request"]["max_stocks"] == 20
    assert captured["publish"] is True
    assert captured["notify"] is True
    assert captured["auto_upside"] is True
    assert captured["max_stocks"] == 20
    assert captured["end_time"] > captured["start_time"]


def test_catalyst_valuation_report_job_endpoint_submits(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def fake_submit(config, request):
        captured["publish"] = request.publish
        captured["notify"] = request.notify
        captured["auto_upside"] = request.auto_upside
        captured["max_stocks"] = request.max_stocks
        return DerivedJobItem(
            job_type="catalyst_valuation_report",
            run_id="run-catalyst-manual",
            reused_existing=False,
            status="running",
        )

    monkeypatch.setattr(
        "radar.web.server.routers.catalyst_valuation_report.submit_catalyst_valuation_report_job",
        fake_submit,
    )

    response = TestClient(create_app(_config(tmp_path))).post(
        "/api/catalyst-valuation-report/jobs",
        json={
            "start_time": "2026-06-28T19:00:00",
            "end_time": "2026-06-28T20:00:00",
            "limit": 200,
            "publish": True,
            "notify": True,
        },
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["job_type"] == "catalyst_valuation_report"
    assert item["run_id"] == "run-catalyst-manual"
    assert captured == {"publish": True, "notify": True, "auto_upside": False, "max_stocks": None}


def test_catalyst_valuation_report_job_records_bark_error_as_partial_failed(monkeypatch, tmp_path):
    config = _config(tmp_path)
    start_time = datetime.fromisoformat("2026-06-28T09:00:00")
    end_time = datetime.fromisoformat("2026-06-28T10:00:00")
    report = CatalystValuationReport(
        generated_at=end_time,
        start_time=start_time,
        end_time=end_time,
        total_feed_items=25,
        total_candidate_stocks=102,
        total_stocks=3,
    )
    result = CatalystValuationReportRunResult(
        report=report,
        local_html_path=tmp_path / "report.html",
        published_url="https://example.com/report.html",
        bark_sent=False,
        bark_error="调用 Bark 超时",
    )
    run_id = start_run(
        config.database_path,
        kind=CATALYST_VALUATION_REPORT_RUN_KIND,
        target="test-target",
    )
    request = CatalystValuationReportJobRequest(
        start_time=start_time,
        end_time=end_time,
        publish=True,
        notify=True,
    )

    monkeypatch.setattr(
        "radar.web.server.catalyst_valuation_report_jobs.run_catalyst_valuation_report",
        lambda *args, **kwargs: result,
    )

    _run_catalyst_valuation_report_job(config, request, run_id)

    run = get_run(config.database_path, run_id)
    assert run is not None
    assert run.status == "partial_failed"
    assert run.raw_count == 25
    assert run.stored_count == 3
    assert run.filtered_count == 99
    assert run.error_message == "Bark 通知失败: 调用 Bark 超时"
    assert run.metadata["published_url"] == "https://example.com/report.html"
    assert run.metadata["report_id"]
    assert run.metadata["bark_sent"] is False
    assert run.metadata["bark_error"] == "调用 Bark 超时"
    archived = get_catalyst_valuation_report(config.reports_database_path, run.metadata["report_id"])
    assert archived is not None
    assert archived.status == "partial_failed"
    assert archived.bark_error == "调用 Bark 超时"


def test_catalyst_valuation_report_job_starts_auto_upside_chat(monkeypatch, tmp_path):
    config = _config(tmp_path)
    start_time = datetime.fromisoformat("2026-06-28T09:00:00")
    end_time = datetime.fromisoformat("2026-06-28T10:00:00")
    report = CatalystValuationReport(
        generated_at=end_time,
        start_time=start_time,
        end_time=end_time,
        total_feed_items=25,
        total_candidate_stocks=3,
        total_stocks=1,
        stocks=[
            CatalystValuationStockContext(
                stock_key="300476.SZ",
                ts_code="300476.SZ",
                stock_name="胜宏科技",
                first_message_time=datetime.fromisoformat("2026-06-28T09:30:00"),
                latest_message_time=datetime.fromisoformat("2026-06-28T09:40:00"),
            )
        ],
    )
    result = CatalystValuationReportRunResult(
        report=report,
        local_html_path=tmp_path / "report.html",
        published_url="https://example.com/report.html",
        bark_sent=True,
    )
    run_id = start_run(
        config.database_path,
        kind=CATALYST_VALUATION_REPORT_RUN_KIND,
        target="test-target",
    )
    request = CatalystValuationReportJobRequest(
        start_time=start_time,
        end_time=end_time,
        publish=True,
        notify=True,
        auto_upside=True,
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "radar.web.server.catalyst_valuation_report_jobs.run_catalyst_valuation_report",
        lambda *args, **kwargs: result,
    )

    def fake_submit(config, *, report, report_id, parent_run_id, published_url):
        captured["report_id"] = report_id
        captured["parent_run_id"] = parent_run_id
        captured["published_url"] = published_url
        return "chat-run-upside"

    monkeypatch.setattr(
        "radar.web.server.catalyst_valuation_report_jobs.submit_catalyst_valuation_upside_chat_run",
        fake_submit,
    )

    _run_catalyst_valuation_report_job(config, request, run_id)

    run = get_run(config.database_path, run_id)
    assert run is not None
    assert run.status == "succeeded"
    assert run.metadata["auto_upside"] is True
    assert run.metadata["auto_upside_chat_run_id"] == "chat-run-upside"
    assert captured["parent_run_id"] == run_id
    assert captured["published_url"] == "https://example.com/report.html"
    assert captured["report_id"] == run.metadata["report_id"]


def test_catalyst_valuation_report_archive_endpoints_send_bark(monkeypatch, tmp_path):
    from radar.core.chat import ChatRunStore, ChatSessionStore

    config = _config(tmp_path)
    start_time = datetime.fromisoformat("2026-06-28T09:00:00")
    end_time = datetime.fromisoformat("2026-06-28T10:00:00")
    report = CatalystValuationReport(
        generated_at=end_time,
        start_time=start_time,
        end_time=end_time,
        total_feed_items=5,
        total_candidate_stocks=2,
        total_stocks=1,
        stocks=[
            CatalystValuationStockContext(
                stock_key="300476.SZ",
                ts_code="300476.SZ",
                stock_name="胜宏科技",
                first_message_time=datetime.fromisoformat("2026-06-28T09:30:00"),
                latest_message_time=datetime.fromisoformat("2026-06-28T09:40:00"),
                evidence=[
                    CatalystValuationEvidence(
                        message_id="m1",
                        source="个人群",
                        sender="tester",
                        group_name="东财策略",
                        message_time=datetime.fromisoformat("2026-06-28T09:30:00"),
                        latest_message_time=datetime.fromisoformat("2026-06-28T09:40:00"),
                        content="胜宏科技 新签订单 10 亿。",
                        matched_terms=["新签订单"],
                        valuation_terms=["订单"],
                        valuation_numbers=["10 亿"],
                    )
                ],
            )
        ],
    )
    saved = save_catalyst_valuation_report(
        config.reports_database_path,
        request={"limit": 200, "publish": True, "notify": False},
        result=CatalystValuationReportRunResult(
            report=report,
            local_html_path=tmp_path / "report.html",
            published_url="https://example.com/report.html",
        ),
        run_id="run-archive",
        status="succeeded",
    )
    session = ChatSessionStore.from_config(config).create_session(
        title="估值线索空间测算",
        metadata={"surface": "估值线索", "entity_id": saved.report_id},
    )
    chat_run = ChatRunStore.from_config(config).create_run(
        session.session_id,
        metadata={
            "surface": "估值线索",
            "entity_id": saved.report_id,
            "title": "估值线索空间测算",
            "source_report_id": saved.report_id,
        },
        request={"content": "空间测算"},
    )
    notify_calls: list[str] = []

    def fake_notify(config, report, url):
        notify_calls.append(url)

    monkeypatch.setattr("radar.web.server.routers.catalyst_valuation_report.notify_report", fake_notify)

    client = TestClient(create_app(config))
    list_response = client.get(
        "/api/catalyst-valuation-reports",
        params={"granularity_minutes": 60},
    )
    detail_response = client.get(f"/api/external/catalyst-valuation-reports/{saved.report_id}")
    bark_response = client.post(f"/api/catalyst-valuation-reports/{saved.report_id}/bark")

    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["report_id"] == saved.report_id
    assert list_response.json()["items"][0]["top_stocks"][0]["stock_name"] == "胜宏科技"
    assert list_response.json()["items"][0]["upside_chat_run_id"] == chat_run.run_id
    assert list_response.json()["items"][0]["upside_chat_status"] == "running"
    assert detail_response.status_code == 200
    assert detail_response.json()["item"]["report"]["stocks"][0]["stock_name"] == "胜宏科技"
    assert detail_response.json()["item"]["upside_chat_session_id"] == session.session_id
    assert detail_response.json()["item"]["rendered_html"].startswith("<!doctype html>")
    assert bark_response.status_code == 200
    assert notify_calls == ["https://example.com/report.html"]
    assert bark_response.json()["item"]["bark_sent_at"] is not None
    assert bark_response.json()["notification"]["status"] == "succeeded"


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
