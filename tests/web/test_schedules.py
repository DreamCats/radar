from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from radar.core.config import RadarConfig
from radar.core.storage import start_run
from radar.web.server.app import create_app


def test_schedules_endpoint_seeds_disabled_defaults(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    response = client.get("/api/schedules")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["schedule_id"] for item in items] == [
        "wechat-ingest-incremental",
        "message-classify-incremental",
        "market-anchor-close",
        "analyst-backtest-close",
    ]
    assert all(item["enabled"] is False for item in items)
    assert items[0]["window_preset"] == "yesterday_1500_to_now"


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
