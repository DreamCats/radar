from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from radar.core.config import RadarConfig
from radar.core.models import RawMessage
from radar.core.runs import finish_run, get_run, start_run
from radar.core.store import connect, init_db, upsert_messages
from radar.core.usecases import IngestRangeResult
from radar.web.server.app import create_app


def test_messages_endpoint_reads_paged_messages(tmp_path):
    config = _config(tmp_path)
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, [_message()])
    finally:
        conn.close()

    client = TestClient(create_app(config))
    response = client.get("/api/messages", params={"keyword": "固态", "limit": 10})

    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["message_id"] == "m1"
    assert data["items"][0]["raw_content"] == "固态电池观点"


def test_message_groups_endpoint_reads_distinct_groups(tmp_path):
    config = _config(tmp_path)
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, [_message()])
    finally:
        conn.close()

    client = TestClient(create_app(config))
    response = client.get("/api/message-groups", params={"source": "group_message"})

    assert response.status_code == 200
    assert response.json()["items"][0]["group_name"] == "东财策略"


def test_root_endpoint_points_to_dashboard(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))
    response = client.get("/")

    assert response.status_code == 200
    assert "dashboard 地址" in response.json()["detail"]


def test_runs_endpoint_returns_recent_runs(tmp_path):
    config = _config(tmp_path)
    run_id = start_run(config.database_path, kind="wechat_ingest_range", target="group_message:day")
    finish_run(config.database_path, run_id, raw_count=2, stored_count=1, filtered_count=1)

    client = TestClient(create_app(config))
    response = client.get("/api/runs", params={"limit": 5})

    assert response.status_code == 200
    assert response.json()["items"][0]["run_id"] == run_id


def test_runs_endpoint_marks_stale_ingest_runs(monkeypatch, tmp_path):
    config = _config(tmp_path)
    run_id = start_run(config.database_path, kind="wechat_ingest_range", target="group_message:stale")

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(hours=2)

    monkeypatch.setattr("radar.web.server.ingest_jobs.datetime", FixedDateTime)

    client = TestClient(create_app(config))
    response = client.get("/api/runs", params={"limit": 5})

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["run_id"] == run_id
    assert item["status"] == "failed"
    assert "过期" in item["error_message"]


def test_ingest_endpoint_invokes_usecase(monkeypatch, tmp_path):
    config = _config(tmp_path)
    calls: list[dict] = []

    def fake_ingest(config, *, source_key, start_time, end_time, force, chunk_hours, concurrency):
        calls.append(
            {
                "source_key": source_key,
                "start_time": start_time,
                "end_time": end_time,
                "force": force,
                "chunk_hours": chunk_hours,
                "concurrency": concurrency,
            }
        )
        return IngestRangeResult(
            source_key=source_key,
            source="个人群",
            start_time=start_time,
            end_time=end_time,
            chunk_count=1,
            skipped_count=0,
            raw_count=3,
            filtered_count=1,
            stored_count=2,
            run_id="run-123",
        )

    monkeypatch.setattr("radar.web.server.routers.ingest.ingest_wechat_range", fake_ingest)

    client = TestClient(create_app(config))
    response = client.post(
        "/api/ingest/wechat",
        json={
            "source": "group_message",
            "start_time": "2026-06-03T00:00:00",
            "end_time": "2026-06-04T00:00:00",
            "force": True,
            "chunk_hours": 1,
            "concurrency": 4,
        },
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["stored_count"] == 2
    assert calls == [
        {
            "source_key": "group_message",
            "start_time": datetime.fromisoformat("2026-06-03T00:00:00"),
            "end_time": datetime.fromisoformat("2026-06-04T00:00:00"),
            "force": True,
            "chunk_hours": 1,
            "concurrency": 4,
        }
    ]


def test_ingest_jobs_endpoint_starts_and_reuses_running_job(monkeypatch, tmp_path):
    config = _config(tmp_path)
    calls: list[dict] = []

    def fake_ingest(config, *, source_key, start_time, end_time, force, chunk_hours, concurrency, run_id):
        calls.append(
            {
                "source_key": source_key,
                "start_time": start_time,
                "end_time": end_time,
                "force": force,
                "chunk_hours": chunk_hours,
                "concurrency": concurrency,
                "run_id": run_id,
            }
        )

    monkeypatch.setattr("radar.web.server.ingest_jobs.ingest_wechat_range", fake_ingest)

    client = TestClient(create_app(config))
    payload = {
        "source": "group_message",
        "start_time": "2026-06-03T00:00:00",
        "end_time": "2026-06-04T00:00:00",
        "force": False,
        "chunk_hours": 1,
        "concurrency": 4,
    }
    response = client.post("/api/ingest/wechat/jobs", json=payload)

    assert response.status_code == 200
    first = response.json()["items"][0]
    assert first["status"] == "running"
    assert first["reused_existing"] is False
    assert get_run(config.database_path, first["run_id"]) is not None

    response = client.post("/api/ingest/wechat/jobs", json=payload)
    second = response.json()["items"][0]

    assert second["run_id"] == first["run_id"]
    assert second["reused_existing"] is True


def _config(tmp_path) -> RadarConfig:
    return RadarConfig(
        storage={
            "data_dir": tmp_path / "data",
            "database": tmp_path / "radar.sqlite3",
        }
    )


def _message() -> RawMessage:
    return RawMessage(
        message_id="m1",
        source="个人群",
        sender="tester",
        message_time=datetime.fromisoformat("2026-06-04T10:00:00"),
        raw_content="固态电池观点",
        group_name="东财策略",
        fetch_time=datetime.fromisoformat("2026-06-04T10:01:00"),
        fetch_window="20260604090000-20260604110000",
    )
