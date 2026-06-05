from __future__ import annotations

from datetime import datetime, timedelta
from threading import Event

from fastapi.testclient import TestClient

from radar.core.config import RadarConfig
from radar.core.models import MessageClassification, RawMessage
from radar.core.runs import finish_run, get_run, start_run
from radar.core.store import connect, init_db, upsert_message_classifications, upsert_messages
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


def test_messages_overview_endpoint_returns_aggregates(tmp_path):
    config = _config(tmp_path)
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(
            conn,
            [
                _message("m1", "2026-06-04T10:00:00", "个人群", "东财策略"),
                _message("m2", "2026-06-04T09:00:00", "个人群", "东财策略"),
                _message("m3", "2026-06-03T09:00:00", "个人消息", None, sender="friend"),
            ],
        )
    finally:
        conn.close()

    client = TestClient(create_app(config))
    response = client.get("/api/messages/overview", params={"days": 2, "top_limit": 3})

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total_count"] == 3
    assert data["summary"]["group_message_count"] == 2
    assert data["summary"]["personal_message_count"] == 1
    assert [item["total_count"] for item in data["date_buckets"]] == [1, 2]
    assert data["top_groups"][0]["group_name"] == "东财策略"
    assert data["top_groups"][0]["count"] == 2


def test_conversations_endpoint_omits_message_count(tmp_path):
    config = _config(tmp_path)
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, [_message()])
    finally:
        conn.close()

    client = TestClient(create_app(config))
    for params in ({"source": "group_message"}, {"source": "group_message", "keyword": "固态"}):
        response = client.get("/api/conversations", params=params)

        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["title"] == "东财策略"
        assert "message_count" not in item


def test_organize_classifications_endpoint_returns_clusters(tmp_path):
    config = _config(tmp_path)
    message = _message()
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, [message])
        upsert_message_classifications(conn, [_classification(message, "research", 0.92, "研究观点")])
    finally:
        conn.close()

    client = TestClient(create_app(config))
    response = client.get("/api/organize/classifications", params={"source": "group_message"})

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total_count"] == 1
    assert data["clusters"][0]["category"] == "research"
    assert data["clusters"][0]["label"] == "研究观点"
    assert data["clusters"][0]["evidence"][0]["message_id"] == "m1"


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


def test_classify_jobs_endpoint_starts_and_reuses_running_job(monkeypatch, tmp_path):
    config = _config(
        tmp_path,
        llm={
            "providers": {
                "provider-a": {"protocol": "openai", "secret_ref": "a", "model": "model-a"},
                "provider-b": {"protocol": "anthropic", "secret_ref": "b", "model": "model-b"},
            }
        },
    )
    calls: list[dict] = []
    started = Event()
    release = Event()

    def fake_classify(
        config,
        *,
        source,
        start_time,
        end_time,
        chunk_hours,
        limit,
        force,
        use_llm,
        provider_name,
        provider_names,
        batch_size,
        max_concurrency,
        retry,
        low_confidence_threshold,
        run_id,
    ):
        calls.append(
            {
                "source": source,
                "start_time": start_time,
                "end_time": end_time,
                "chunk_hours": chunk_hours,
                "limit": limit,
                "force": force,
                "use_llm": use_llm,
                "provider_name": provider_name,
                "provider_names": provider_names,
                "batch_size": batch_size,
                "max_concurrency": max_concurrency,
                "retry": retry,
                "low_confidence_threshold": low_confidence_threshold,
                "run_id": run_id,
            }
        )
        started.set()
        release.wait(timeout=2)

    monkeypatch.setattr("radar.web.server.classify_jobs.classify_messages_range", fake_classify)

    client = TestClient(create_app(config))
    payload = {
        "source": "group_message",
        "start_time": "2026-06-04T10:00:00",
        "end_time": "2026-06-04T11:00:00",
        "force": False,
        "chunk_hours": 1,
        "limit": 200,
        "batch_size": 8,
        "retry": "needs_review",
        "low_confidence_threshold": 0.7,
    }
    response = client.post("/api/classify/messages/jobs", json=payload)

    assert response.status_code == 200
    first = response.json()["items"][0]
    assert started.wait(timeout=1)
    assert first["status"] == "running"
    assert first["source"] == "个人群"
    assert first["reused_existing"] is False
    assert get_run(config.database_path, first["run_id"]) is not None

    response = client.post("/api/classify/messages/jobs", json=payload)
    second = response.json()["items"][0]

    assert second["run_id"] == first["run_id"]
    assert second["reused_existing"] is True

    different_payload = payload | {"end_time": "2026-06-04T12:00:00"}
    response = client.post("/api/classify/messages/jobs", json=different_payload)
    third = response.json()["items"][0]

    assert third["run_id"] == first["run_id"]
    assert third["reused_existing"] is True
    release.set()
    assert calls[0] == {
        "source": "个人群",
        "start_time": datetime.fromisoformat("2026-06-04T10:00:00"),
        "end_time": datetime.fromisoformat("2026-06-04T11:00:00"),
        "chunk_hours": 1,
        "limit": 200,
        "force": False,
        "use_llm": True,
        "provider_name": None,
        "provider_names": ["provider-a", "provider-b"],
        "batch_size": 8,
        "max_concurrency": 10,
        "retry": "needs_review",
        "low_confidence_threshold": 0.7,
        "run_id": first["run_id"],
    }


def _config(tmp_path, **overrides) -> RadarConfig:
    return RadarConfig(
        storage={
            "data_dir": tmp_path / "data",
            "database": tmp_path / "radar.sqlite3",
        },
        **overrides,
    )


def _message(
    message_id: str = "m1",
    message_time: str = "2026-06-04T10:00:00",
    source: str = "个人群",
    group_name: str | None = "东财策略",
    *,
    sender: str = "tester",
) -> RawMessage:
    return RawMessage(
        message_id=message_id,
        source=source,
        sender=sender,
        message_time=datetime.fromisoformat(message_time),
        raw_content="固态电池观点",
        group_name=group_name,
        fetch_time=datetime.fromisoformat("2026-06-04T10:01:00"),
        fetch_window="20260604090000-20260604110000",
    )


def _classification(message: RawMessage, category: str, confidence: float, reason: str) -> MessageClassification:
    now = datetime.fromisoformat("2026-06-04T12:00:00")
    return MessageClassification(
        message_id=message.message_id,
        category=category,
        confidence=confidence,
        reason=reason,
        status="auto",
        classifier_type="llm",
        llm_provider="test-provider",
        prompt_version="test",
        classifier_version="test",
        created_at=now,
        updated_at=now,
    )
