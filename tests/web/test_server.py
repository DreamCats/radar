from __future__ import annotations

import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from threading import Event
from time import sleep

from fastapi.testclient import TestClient

from radar.core.config import RadarConfig
from radar.core.models import MessageClassification, RawMessage
from radar.core.runs import finish_run, get_run, start_run
from radar.core.store import connect, init_db, upsert_message_classifications, upsert_messages
from radar.core.usecases import IngestRangeResult
from radar.core.usecases.aggregation import AggregateTopicsResult, RefineAggregateTopicsResult, RefinedTheme
from radar.core.usecases.aggregation.storage import store_refine_result
from radar.core.usecases.recommendation_backtest import (
    RecommendationBacktestSummaryResult,
    RecommendationBacktestSummaryRow,
)
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


def test_organize_classifications_endpoint_can_skip_evidence(tmp_path):
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
    response = client.get("/api/organize/classifications", params={"evidence_limit": 0})

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total_count"] == 1
    assert data["clusters"][0]["evidence"] == []


def test_organize_classifications_endpoint_hides_low_value_rows(tmp_path):
    config = _config(tmp_path)
    messages = [
        _message(message_id="m1", message_time="2026-06-04T10:00:00"),
        _message(message_id="m2", message_time="2026-06-04T10:01:00"),
        _message(message_id="m3", message_time="2026-06-04T10:02:00"),
        _message(message_id="m4", message_time="2026-06-04T10:03:00"),
    ]
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, messages)
        upsert_message_classifications(
            conn,
            [
                _classification(messages[0], "research", 0.92, "研究观点"),
                _classification(messages[1], "unknown", 0.20, "信息不足", status="needs_review"),
                _classification(messages[2], "chat", 0.90, "闲聊", status="ignored"),
                _classification(messages[3], "research", 0.70, "基本确定"),
            ],
        )
    finally:
        conn.close()

    client = TestClient(create_app(config))
    response = client.get("/api/organize/classifications")

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["classified_count"] == 4
    assert data["summary"]["total_count"] == 1
    assert data["summary"]["low_confidence_count"] == 2
    assert data["summary"]["noise_count"] == 1
    assert data["summary"]["hidden_count"] == 3
    assert [cluster["category"] for cluster in data["clusters"]] == ["research"]


def test_organize_classification_evidence_endpoint_pages_results(tmp_path):
    config = _config(tmp_path)
    messages = [
        _message(message_id="m1", message_time="2026-06-04T10:00:00"),
        _message(message_id="m2", message_time="2026-06-04T10:01:00"),
        _message(message_id="m3", message_time="2026-06-04T10:02:00"),
    ]
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, messages)
        upsert_message_classifications(
            conn,
            [
                _classification(messages[0], "research", 0.92, "研究观点"),
                _classification(messages[1], "research", 0.92, "研究观点"),
                _classification(messages[2], "research", 0.92, "研究观点"),
            ],
        )
    finally:
        conn.close()

    client = TestClient(create_app(config))
    first = client.get("/api/organize/classifications/evidence", params={"category": "research", "limit": 2})

    assert first.status_code == 200
    first_data = first.json()
    assert [item["message_id"] for item in first_data["items"]] == ["m3", "m2"]
    assert first_data["next_cursor_id"] == "m2"

    second = client.get(
        "/api/organize/classifications/evidence",
        params={
            "category": "research",
            "limit": 2,
            "cursor_time": first_data["next_cursor_time"],
            "cursor_id": first_data["next_cursor_id"],
        },
    )

    assert second.status_code == 200
    second_data = second.json()
    assert [item["message_id"] for item in second_data["items"]] == ["m1"]
    assert second_data["next_cursor_id"] is None


def test_organize_classification_evidence_endpoint_requires_cursor_pair(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))
    response = client.get(
        "/api/organize/classifications/evidence",
        params={"category": "research", "cursor_id": "m1"},
    )

    assert response.status_code == 400
    assert "cursor_time" in response.json()["detail"]


def test_organize_aggregates_endpoint_returns_latest_result_with_evidence(tmp_path):
    config = _config(tmp_path)
    messages = [
        _message(message_id="m1", message_time="2026-06-04T10:00:00"),
        _message(message_id="m2", message_time="2026-06-04T10:01:00"),
    ]
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, messages)
        upsert_message_classifications(
            conn,
            [
                _classification(messages[0], "research", 0.92, "研究观点"),
                _classification(messages[1], "recommendation", 0.93, "投资推荐"),
            ],
        )
        store_refine_result(conn, _refine_result("run-refine", ["m1", "m2"]))
    finally:
        conn.close()

    client = TestClient(create_app(config))
    response = client.get(
        "/api/organize/aggregates",
        params={
            "start_time": "2026-06-04T09:00:00",
            "end_time": "2026-06-04T12:00:00",
            "evidence_limit": 1,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["result"]["run_id"] == "run-refine"
    assert data["result"]["theme_count"] == 1
    assert data["themes"][0]["theme_name"] == "固态电池聚类"
    assert data["themes"][0]["priority_score"] > 0
    assert [item["message_id"] for item in data["themes"][0]["evidence"]] == ["m2"]


def test_organize_aggregate_evidence_endpoint_pages_results(tmp_path):
    config = _config(tmp_path)
    messages = [
        _message(message_id="m1", message_time="2026-06-04T10:00:00"),
        _message(message_id="m2", message_time="2026-06-04T10:01:00"),
        _message(message_id="m3", message_time="2026-06-04T10:02:00"),
    ]
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, messages)
        upsert_message_classifications(conn, [_classification(message, "research", 0.92, "研究观点") for message in messages])
        store_refine_result(conn, _refine_result("run-refine", ["m1", "m2", "m3"]))
    finally:
        conn.close()

    client = TestClient(create_app(config))
    first = client.get("/api/organize/aggregates/evidence", params={"run_id": "run-refine", "theme_index": 0, "limit": 2})

    assert first.status_code == 200
    first_data = first.json()
    assert [item["message_id"] for item in first_data["items"]] == ["m3", "m2"]
    assert first_data["next_cursor_id"] == "m2"

    second = client.get(
        "/api/organize/aggregates/evidence",
        params={
            "run_id": "run-refine",
            "theme_index": 0,
            "limit": 2,
            "cursor_time": first_data["next_cursor_time"],
            "cursor_id": first_data["next_cursor_id"],
        },
    )

    assert second.status_code == 200
    second_data = second.json()
    assert [item["message_id"] for item in second_data["items"]] == ["m1"]
    assert second_data["next_cursor_id"] is None


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


def test_anchor_jobs_endpoint_starts_and_reuses_running_job(monkeypatch, tmp_path):
    config = _config(tmp_path)
    calls: list[dict] = []
    started = Event()
    release = Event()

    def fake_anchor(config, *, trade_date, source, categories, min_classification_confidence, start_time, end_time,
                    chunk_hours, limit, force, max_anchors_per_message, run_id):
        calls.append(
            {
                "trade_date": trade_date,
                "source": source,
                "categories": categories,
                "min_classification_confidence": min_classification_confidence,
                "start_time": start_time,
                "end_time": end_time,
                "chunk_hours": chunk_hours,
                "limit": limit,
                "force": force,
                "max_anchors_per_message": max_anchors_per_message,
                "run_id": run_id,
            }
        )
        started.set()
        release.wait(timeout=2)

    monkeypatch.setattr("radar.web.server.aggregate_jobs.ensure_market_anchors", lambda *args, **kwargs: None)
    monkeypatch.setattr("radar.web.server.aggregate_jobs.anchor_messages_range", fake_anchor)

    client = TestClient(create_app(config))
    payload = {
        "trade_date": "20260604",
        "source": "group_message",
        "start_time": "2026-06-04T10:00:00",
        "end_time": "2026-06-04T11:00:00",
        "force": True,
        "chunk_hours": 1,
        "limit": 200,
        "categories": ["research", "recommendation"],
        "min_classification_confidence": 0.75,
        "max_anchors": 8,
    }
    response = client.post("/api/anchor/messages/jobs", json=payload)

    assert response.status_code == 200
    first = response.json()["items"][0]
    assert started.wait(timeout=1)
    assert first["job_type"] == "anchor"
    assert first["status"] == "running"
    assert first["reused_existing"] is False
    assert get_run(config.database_path, first["run_id"]) is not None

    response = client.post("/api/anchor/messages/jobs", json=payload)
    second = response.json()["items"][0]

    assert second["run_id"] == first["run_id"]
    assert second["reused_existing"] is True
    release.set()
    assert calls[0] == {
        "trade_date": "20260604",
        "source": "个人群",
        "categories": ["research", "recommendation"],
        "min_classification_confidence": 0.75,
        "start_time": datetime.fromisoformat("2026-06-04T10:00:00"),
        "end_time": datetime.fromisoformat("2026-06-04T11:00:00"),
        "chunk_hours": 1,
        "limit": 200,
        "force": True,
        "max_anchors_per_message": 8,
        "run_id": first["run_id"],
    }


def test_aggregate_refine_jobs_endpoint_starts_job(monkeypatch, tmp_path):
    config = _config(tmp_path)
    calls: list[dict] = []
    started = Event()
    release = Event()

    def fake_refine(config, *, trade_date, source, categories, min_classification_confidence, start_time, end_time,
                    min_messages, candidate_limit, evidence_limit, batch_size, max_concurrency,
                    provider_name, provider_names, force, run_id):
        calls.append(
            {
                "trade_date": trade_date,
                "source": source,
                "categories": categories,
                "min_classification_confidence": min_classification_confidence,
                "start_time": start_time,
                "end_time": end_time,
                "min_messages": min_messages,
                "candidate_limit": candidate_limit,
                "evidence_limit": evidence_limit,
                "batch_size": batch_size,
                "max_concurrency": max_concurrency,
                "provider_name": provider_name,
                "provider_names": provider_names,
                "force": force,
                "run_id": run_id,
            }
        )
        started.set()
        release.wait(timeout=2)

    monkeypatch.setattr("radar.web.server.aggregate_jobs.refine_aggregate_topics", fake_refine)

    client = TestClient(create_app(config))
    payload = {
        "trade_date": "20260604",
        "source": "all",
        "start_time": "2026-06-04T10:00:00",
        "end_time": "2026-06-04T11:00:00",
        "force": False,
        "categories": ["research"],
        "min_classification_confidence": 0.7,
        "min_messages": 2,
        "candidate_limit": 20,
        "evidence_limit": 2,
        "batch_size": 5,
        "max_concurrency": 10,
        "provider_names": ["p1", "p2"],
    }
    response = client.post("/api/aggregate/refine/jobs", json=payload)

    assert response.status_code == 200
    first = response.json()["items"][0]
    assert started.wait(timeout=1)
    assert first["job_type"] == "aggregate_refine"
    assert first["status"] == "running"
    assert get_run(config.database_path, first["run_id"]) is not None
    release.set()
    assert calls[0]["source"] is None
    assert calls[0]["provider_names"] == ["p1", "p2"]
    assert calls[0]["run_id"] == first["run_id"]


def test_aggregate_refine_results_endpoint_returns_recent_results(tmp_path):
    config = _config(tmp_path)
    local_result = AggregateTopicsResult(
        trade_date="20260604",
        extractor_version="test",
        start_time=datetime.fromisoformat("2026-06-04T10:00:00"),
        end_time=datetime.fromisoformat("2026-06-04T11:00:00"),
        categories=["research"],
        min_classification_confidence=0.7,
        scoped_message_count=2,
        anchored_message_count=2,
        topic_count=1,
        topics=[],
    )
    result = RefineAggregateTopicsResult(
        run_id="run-refine",
        input_hash="hash-refine",
        status="succeeded",
        trade_date="20260604",
        extractor_version="test",
        prompt_version="test-prompt",
        candidate_count=1,
        theme_count=1,
        local_result=local_result,
        themes=[RefinedTheme(theme_name="玻璃基板", actionability_score=80)],
    )
    conn = connect(config.database_path)
    try:
        init_db(conn)
        store_refine_result(conn, result)
    finally:
        conn.close()

    client = TestClient(create_app(config))
    response = client.get("/api/aggregate/refine/results", params={"limit": 5})

    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["input_hash"] == "hash-refine"
    assert data["items"][0]["themes"][0]["theme_name"] == "玻璃基板"


def test_recommendation_backtest_jobs_endpoint_starts_and_reuses_running_job(monkeypatch, tmp_path):
    config = _config(tmp_path)
    calls: list[dict] = []
    started = Event()
    release = Event()

    def fake_backtest(config, *, as_of, window_days, start_time, end_time, windows, source, min_classification_confidence,
                      extractor_version, benchmark_ts_code, force, run_id):
        calls.append(
            {
                "as_of": as_of,
                "window_days": window_days,
                "start_time": start_time,
                "end_time": end_time,
                "windows": windows,
                "source": source,
                "min_classification_confidence": min_classification_confidence,
                "benchmark_ts_code": benchmark_ts_code,
                "force": force,
                "run_id": run_id,
            }
        )
        started.set()
        release.wait(timeout=2)

    monkeypatch.setattr("radar.web.server.backtest_jobs.refresh_recommendation_backtests", fake_backtest)

    client = TestClient(create_app(config))
    payload = {
        "as_of": "2026-06-05",
        "window_days": 30,
        "start_time": "2026-05-07T00:00:00",
        "end_time": "2026-06-05T15:30:00",
        "windows": [1, 2, 3, 5],
        "source": "group_message",
        "min_classification_confidence": 0.7,
        "benchmark_ts_code": "000300.SH",
        "force": False,
    }
    response = client.post("/api/recommendation/backtest/jobs", json=payload)

    assert response.status_code == 200
    first = response.json()["items"][0]
    assert started.wait(timeout=1)
    assert first["job_type"] == "recommendation_backtest"
    assert first["status"] == "running"
    assert first["reused_existing"] is False
    assert get_run(config.database_path, first["run_id"]) is not None

    response = client.post("/api/recommendation/backtest/jobs", json=payload)
    second = response.json()["items"][0]

    assert second["run_id"] == first["run_id"]
    assert second["reused_existing"] is True
    release.set()
    assert calls[0]["source"] == "个人群"
    assert calls[0]["start_time"] == datetime.fromisoformat("2026-05-07T00:00:00")
    assert calls[0]["end_time"] == datetime.fromisoformat("2026-06-05T15:30:00")
    assert calls[0]["windows"] == [1, 2, 3, 5]
    assert calls[0]["benchmark_ts_code"] == "000300.SH"
    assert calls[0]["run_id"] == first["run_id"]


def test_source_radar_jobs_endpoint_starts_and_reuses_running_job(monkeypatch, tmp_path):
    config = _config(tmp_path)
    extract_calls: list[dict] = []
    scan_calls: list[dict] = []
    started = Event()
    release = Event()

    def fake_extract(config, *, start_time, end_time, limit, force, batch_size, max_concurrency, provider_name, provider_names):
        extract_calls.append(
            {
                "start_time": start_time,
                "end_time": end_time,
                "limit": limit,
                "force": force,
                "batch_size": batch_size,
                "max_concurrency": max_concurrency,
                "provider_name": provider_name,
                "provider_names": provider_names,
            }
        )
        started.set()
        release.wait(timeout=2)
        return SimpleNamespace(scanned_count=3, extracted_count=2, inserted_count=2, failed_llm_batches=0)

    def fake_scan(config, *, start_time, end_time, as_of_time, lookback_days, limit, save_snapshot):
        scan_calls.append(
            {
                "start_time": start_time,
                "end_time": end_time,
                "as_of_time": as_of_time,
                "lookback_days": lookback_days,
                "limit": limit,
                "save_snapshot": save_snapshot,
            }
        )
        return SimpleNamespace(candidate_count=4, candidates=[object(), object()])

    monkeypatch.setattr("radar.web.server.source_jobs.extract_source_structures", fake_extract)
    monkeypatch.setattr("radar.web.server.source_jobs.scan_source_signals", fake_scan)

    client = TestClient(create_app(config))
    payload = {
        "start_time": "2026-06-06T00:00:00",
        "end_time": "2026-06-06T23:59:59",
        "force": False,
        "per_day_limit": 500,
        "batch_size": 8,
        "max_concurrency": 10,
        "lookback_days": 60,
        "scan_limit": 20,
    }
    response = client.post("/api/source/radar/jobs", json=payload)

    assert response.status_code == 200
    first = response.json()["items"][0]
    assert started.wait(timeout=1)
    assert first["job_type"] == "source_radar"
    assert first["status"] == "running"
    assert first["reused_existing"] is False
    assert get_run(config.database_path, first["run_id"]) is not None

    response = client.post("/api/source/radar/jobs", json=payload)
    second = response.json()["items"][0]

    assert second["run_id"] == first["run_id"]
    assert second["reused_existing"] is True
    release.set()
    for _ in range(20):
        if scan_calls:
            break
        sleep(0.05)
    assert extract_calls[0]["start_time"] == datetime.fromisoformat("2026-06-06T00:00:00")
    assert extract_calls[0]["end_time"] == datetime.fromisoformat("2026-06-06T23:59:59")
    assert extract_calls[0]["limit"] == 500
    assert extract_calls[0]["max_concurrency"] == 10
    assert scan_calls[0]["save_snapshot"] is True
    assert scan_calls[0]["lookback_days"] == 60


def test_recommendation_backtest_summary_endpoint_returns_rows(monkeypatch, tmp_path):
    config = _config(tmp_path)
    calls: list[dict] = []

    def fake_summary(config, *, start_time, end_time, group_by, windows, source, min_count, limit):
        calls.append(
            {
                "start_time": start_time,
                "end_time": end_time,
                "group_by": group_by,
                "windows": windows,
                "source": source,
                "min_count": min_count,
                "limit": limit,
            }
        )
        return RecommendationBacktestSummaryResult(
            start_time=start_time,
            end_time=end_time,
            group_by=group_by,
            windows=windows,
            row_count=1,
            rows=[
                RecommendationBacktestSummaryRow(
                    key="analyst-1|industry|白酒",
                    analyst_id="analyst-1",
                    analyst_display_name="张三-分析师",
                    sector_anchor_type="industry",
                    sector_name="白酒",
                    event_count=4,
                    metrics={"sample_count_t5": 3, "win_rate_t5": 1.0},
                )
            ],
        )

    monkeypatch.setattr("radar.web.server.routers.backtest.summarize_recommendation_backtests", fake_summary)

    client = TestClient(create_app(config))
    response = client.get(
        "/api/recommendation/backtest/summary",
        params={
            "start_time": "2026-05-01T00:00:00",
            "end_time": "2026-06-06T00:00:00",
            "source": "group_message",
            "group_by": "analyst_sector",
            "min_count": 3,
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["row_count"] == 1
    assert data["rows"][0]["analyst_display_name"] == "张三-分析师"
    assert data["rows"][0]["sector_name"] == "白酒"
    assert calls[0]["group_by"] == "analyst_sector"
    assert calls[0]["source"] == "个人群"
    assert calls[0]["windows"] == [1, 2, 3, 5]
    assert calls[0]["min_count"] == 3
    assert calls[0]["limit"] == 10


def test_strategy_source_radar_endpoint_returns_latest_snapshot(tmp_path):
    config = _config(tmp_path)
    conn = connect(config.database_path)
    try:
        init_db(conn)
        _insert_source_signal_snapshot(conn, "old", "2026-06-05T15:00:00", "旧概念", 55)
        _insert_source_signal_snapshot(conn, "new", "2026-06-07T15:00:00", "AI服务器MLCC", 88)
    finally:
        conn.close()

    client = TestClient(create_app(config))
    response = client.get("/api/strategy/source-radar", params={"limit": 10})

    assert response.status_code == 200
    data = response.json()
    assert data["as_of_time"] == "2026-06-07T15:00:00"
    assert data["item_count"] == 1
    assert data["available_as_of_times"] == ["2026-06-07T15:00:00", "2026-06-05T15:00:00"]
    assert data["items"][0]["anchor_span"] == "AI服务器MLCC"
    assert data["items"][0]["score"] == 88


def test_strategy_source_radar_validation_endpoint_tracks_signal_evolution(tmp_path):
    config = _config(tmp_path)
    conn = connect(config.database_path)
    try:
        init_db(conn)
        _insert_source_signal_snapshot(conn, "ai-mlcc", "2026-06-01T15:00:00", "AI服务器MLCC", 70)
        _insert_source_signal_snapshot(
            conn,
            "ai-mlcc",
            "2026-06-03T15:00:00",
            "AI服务器MLCC",
            91,
            status="mapped",
            mapped_stocks=["风华高科"],
            followup_senders=3,
        )
        _insert_source_signal_snapshot(conn, "cold", "2026-06-01T15:00:00", "冷门概念", 60)
    finally:
        conn.close()

    client = TestClient(create_app(config))
    response = client.get("/api/strategy/source-radar/validation", params={"window_days": 5, "limit": 10})

    assert response.status_code == 200
    data = response.json()
    assert data["snapshot_count"] == 2
    assert data["signal_count"] == 2
    assert data["spreading_count"] == 1
    assert data["mapped_count"] == 1
    assert data["top_signals"][0]["title"] == "早期AI服务器MLCC"
    assert data["top_signals"][0]["mapped_stocks"] == ["风华高科"]


def _config(tmp_path, **overrides) -> RadarConfig:
    return RadarConfig(
        storage={
            "data_dir": tmp_path / "data",
            "database": tmp_path / "radar.sqlite3",
        },
        **overrides,
    )


def _insert_source_signal_snapshot(
    conn,
    signal_id: str,
    as_of_time: str,
    anchor: str,
    score: int,
    *,
    status: str = "source_seed",
    mapped_stocks: list[str] | None = None,
    followup_senders: int = 0,
) -> None:
    payload = {
        "signal_id": signal_id,
        "status": status,
        "anchor_span": anchor,
        "modifier_span": "早期",
        "novel_span": anchor,
        "relation_type": "modifier-anchor",
        "score": score,
        "novelty_strength": 0.9,
        "earliness_score": 0.8,
        "askability_score": 0.7,
        "trade_score": 0.6,
        "first_message_id": f"m-{signal_id}",
        "first_seen_time": as_of_time,
        "first_sender": "分析师A",
        "first_group_name": "科技群",
        "first_snippet": "早期概念讨论",
        "prior_anchor_mentions": 0,
        "prior_modifier_mentions": 0,
        "prior_exact_mentions": 0,
        "prior_combo_mentions": 0,
        "asof_mentions": 1,
        "asof_groups": 1,
        "asof_senders": 1,
        "followup_groups": 0,
        "followup_senders": followup_senders,
        "mapped_stocks": mapped_stocks or [],
        "ask_question": "是否出现新需求？",
        "evidence": ["历史精确 0 次"],
    }
    conn.execute(
        """
        INSERT INTO source_signal_snapshots (
            snapshot_id, signal_id, status, anchor_span, modifier_span, novel_span,
            relation_type, score, novelty_strength, earliness_score, askability_score,
            trade_score, first_message_id, first_seen_time, as_of_time, payload_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"snap-{signal_id}-{as_of_time}",
            signal_id,
            status,
            anchor,
            "早期",
            anchor,
            "modifier-anchor",
            score,
            0.9,
            0.8,
            0.7,
            0.6,
            f"m-{signal_id}",
            as_of_time,
            as_of_time,
            json.dumps(payload, ensure_ascii=False),
            as_of_time,
        ),
    )
    conn.commit()


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


def _classification(
    message: RawMessage,
    category: str,
    confidence: float,
    reason: str,
    *,
    status: str = "auto",
) -> MessageClassification:
    now = datetime.fromisoformat("2026-06-04T12:00:00")
    return MessageClassification(
        message_id=message.message_id,
        category=category,
        confidence=confidence,
        reason=reason,
        status=status,
        classifier_type="llm",
        llm_provider="test-provider",
        prompt_version="test",
        classifier_version="test",
        created_at=now,
        updated_at=now,
    )


def _refine_result(run_id: str, evidence_ids: list[str]) -> RefineAggregateTopicsResult:
    local_result = AggregateTopicsResult(
        trade_date="20260604",
        extractor_version="test",
        start_time=datetime.fromisoformat("2026-06-04T09:00:00"),
        end_time=datetime.fromisoformat("2026-06-04T12:00:00"),
        categories=["research", "recommendation"],
        min_classification_confidence=0.7,
        scoped_message_count=len(evidence_ids),
        anchored_message_count=len(evidence_ids),
        topic_count=1,
        topics=[],
    )
    return RefineAggregateTopicsResult(
        run_id=run_id,
        input_hash=f"hash-{run_id}",
        status="succeeded",
        trade_date="20260604",
        extractor_version="test",
        prompt_version="test-prompt",
        candidate_count=1,
        theme_count=1,
        llm_batch_count=1,
        failed_llm_batches=0,
        max_concurrency=2,
        local_result=local_result,
        themes=[
            RefinedTheme(
                theme_name="固态电池聚类",
                summary="固态电池观点聚合",
                evidence_message_ids=evidence_ids,
                confidence=0.82,
                actionability_score=78,
            )
        ],
    )
