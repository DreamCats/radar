from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from threading import Event
from time import sleep

from fastapi.testclient import TestClient

from radar.core.config import RadarConfig
from radar.core.models import MessageClassification, RawMessage
from radar.core.storage import finish_run, get_run, start_run
from radar.core.storage import connect, init_db, upsert_message_classifications, upsert_messages
from radar.core.usecases import IngestRangeResult
from radar.core.usecases.recommendation_backtest import (
    RecommendationBacktestSummaryResult,
    RecommendationBacktestSummaryRow,
)
from radar.web.server.app import create_app


def wait_for_run_status(database: Path, run_id: str, status: str, *, timeout: float = 2.0) -> None:
    deadline = datetime.now() + timedelta(seconds=timeout)
    while datetime.now() < deadline:
        run = get_run(database, run_id)
        if run is not None and run.status == status:
            return
        sleep(0.01)
    run = get_run(database, run_id)
    actual = run.status if run is not None else None
    raise AssertionError(f"run {run_id} status did not become {status!r}; actual={actual!r}")


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


def test_auth_disabled_by_default(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    response = client.get("/api/auth/status")

    assert response.status_code == 200
    assert response.json() == {
        "auth_required": False,
        "authenticated": True,
        "username": None,
    }


def test_auth_enabled_gates_api_and_uses_cookie(tmp_path):
    config = _config(
        tmp_path,
        web={"auth": {"enabled": True}},
        secrets={
            "web": {
                "auth": {
                    "username": "maifeng",
                    "password": "secret",
                    "session_secret": "test-secret",
                }
            }
        },
    )
    client = TestClient(create_app(config))

    assert client.get("/api/health").status_code == 200
    assert client.get("/api/runs").status_code == 401
    preflight_response = client.options(
        "/api/ingest/wechat/jobs",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight_response.status_code == 200
    assert preflight_response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert client.post("/api/auth/login", json={"username": "maifeng", "password": "bad"}).status_code == 401

    login_response = client.post(
        "/api/auth/login",
        json={"username": "maifeng", "password": "secret"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["authenticated"] is True

    assert client.get("/api/runs").status_code == 200

    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == 200
    assert logout_response.json()["authenticated"] is False
    assert client.get("/api/runs").status_code == 401


def test_chat_turn_endpoint_creates_session_with_context(tmp_path, monkeypatch):
    from radar.core.chat.events import ChatMessage

    captured: dict[str, object] = {}

    class FakeChatAgent:
        def __init__(self, config):
            self.config = config

        def create_session(self, *, title=None, metadata=None):
            captured["title"] = title
            captured["metadata"] = metadata
            return SimpleNamespace(session_id="session-1")

        def run_turn(self, session_id, content, **kwargs):
            captured["session_id"] = session_id
            captured["content"] = content
            captured["llm_content"] = kwargs.get("llm_content")
            captured["provider_name"] = kwargs.get("provider_name")
            return SimpleNamespace(
                session_id=session_id,
                user_message=ChatMessage(
                    message_id="user-1",
                    role="user",
                    content=content,
                    created_at="2026-06-08T10:00:00",
                ),
                assistant_message=ChatMessage(
                    message_id="assistant-1",
                    role="assistant",
                    content="先看来源质量和反证。",
                    created_at="2026-06-08T10:00:01",
                ),
                tool_messages=[],
            )

    monkeypatch.setattr("radar.web.server.routers.chat.ChatAgent", FakeChatAgent)
    client = TestClient(create_app(_config(tmp_path)))
    response = client.post(
        "/api/chat/turn",
        json={
            "title": "PCB",
            "content": "这个信号怎么看？",
            "provider_name": "deep",
            "context": {"surface": "源头雷达", "entity_id": "sig-1"},
            "metadata": {"surface": "源头雷达"},
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "session-1"
    assert data["assistant_message"]["content"] == "先看来源质量和反证。"
    assert captured["title"] == "PCB"
    assert captured["metadata"] == {"surface": "源头雷达"}
    assert captured["session_id"] == "session-1"
    assert captured["content"] == "这个信号怎么看？"
    assert captured["provider_name"] == "deep"
    assert "这个信号怎么看？" in str(captured["llm_content"])
    assert '"surface":"源头雷达"' in str(captured["llm_content"])


def test_chat_turn_stream_endpoint_returns_sse(tmp_path, monkeypatch):
    from radar.core.chat.events import ChatMessage

    captured: dict[str, object] = {}

    class FakeChatAgent:
        def __init__(self, config):
            self.config = config

        def create_session(self, *, title=None, metadata=None):
            captured["title"] = title
            captured["metadata"] = metadata
            return SimpleNamespace(session_id="session-stream-1")

        def stream_turn(self, session_id, content, **kwargs):
            captured["session_id"] = session_id
            captured["content"] = content
            captured["llm_content"] = kwargs.get("llm_content")
            captured["provider_name"] = kwargs.get("provider_name")
            yield SimpleNamespace(
                type="user_message",
                message=ChatMessage(
                    message_id="user-1",
                    role="user",
                    content=content,
                    created_at="2026-06-08T10:00:00",
                ),
                content=None,
                event=None,
            )
            yield SimpleNamespace(type="assistant_delta", message=None, content="先看", event=None)
            yield SimpleNamespace(
                type="assistant_message",
                message=ChatMessage(
                    message_id="assistant-1",
                    role="assistant",
                    content="先看来源质量。",
                    created_at="2026-06-08T10:00:01",
                ),
                content=None,
                event=None,
            )

    monkeypatch.setattr("radar.web.server.routers.chat.ChatAgent", FakeChatAgent)
    client = TestClient(create_app(_config(tmp_path)))
    response = client.post(
        "/api/chat/turn/stream",
        json={
            "title": "PCB",
            "content": "这个信号怎么看？",
            "provider_name": "deep",
            "context": {"surface": "源头雷达", "entity_id": "sig-1"},
            "metadata": {"surface": "源头雷达"},
        },
    )

    assert response.status_code == 200
    assert "event: session" in response.text
    assert "event: assistant_delta" in response.text
    assert '"content":"先看"' in response.text
    assert captured["session_id"] == "session-stream-1"
    assert captured["content"] == "这个信号怎么看？"
    assert captured["provider_name"] == "deep"
    assert '"surface":"源头雷达"' in str(captured["llm_content"])


def test_chat_model_options_endpoint_uses_shared_llm_config(tmp_path):
    config = _config(
        tmp_path,
        llm={
            "default_provider": "fast",
            "providers": {
                "fast": {"protocol": "openai", "secret_ref": "fast-secret", "model": "gpt-fast"},
                "deep": {"protocol": "anthropic", "secret_ref": "deep-secret", "model": "claude-deep"},
            },
            "task_routing": {"chat": "deep"},
        },
    )
    client = TestClient(create_app(config))

    response = client.get("/api/chat/model-options")

    assert response.status_code == 200
    data = response.json()
    assert data["default_provider_name"] == "deep"
    assert data["items"] == [
        {
            "provider_name": "fast",
            "label": "fast · gpt-fast",
            "protocol": "openai",
            "model": "gpt-fast",
            "context_window_tokens": 256000,
            "is_default": False,
            "thinking_enabled": True,
        },
        {
            "provider_name": "deep",
            "label": "默认 · claude-deep",
            "protocol": "anthropic",
            "model": "claude-deep",
            "context_window_tokens": 256000,
            "is_default": True,
            "thinking_enabled": True,
        },
    ]


def test_chat_sessions_endpoint_lists_file_backed_sessions(tmp_path):
    from radar.core.chat import ChatMessage, ChatSessionStore
    from radar.core.chat.events import new_id

    config = _config(tmp_path)
    store = ChatSessionStore.from_config(config)
    session = store.create_session(title="总览简报", metadata={"surface": "总览"})
    store.append_message(
        session.session_id,
        ChatMessage(
            message_id=new_id(),
            role="user",
            content="今天有什么机会？",
            created_at="2026-06-08T10:00:00",
        ),
    )
    store.append_message(
        session.session_id,
        ChatMessage(
            message_id=new_id(),
            role="assistant",
            content="先看半导体和 MLCC。",
            created_at="2026-06-08T10:00:01",
        ),
    )

    client = TestClient(create_app(config))
    response = client.get("/api/chat/sessions")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["session_id"] == session.session_id
    assert item["title"] == "总览简报"
    assert item["metadata"] == {"surface": "总览"}
    assert item["message_count"] == 2
    assert item["preview"] == "先看半导体和 MLCC。"
    assert item["can_continue"] is False


def test_chat_session_detail_endpoint_restores_messages(tmp_path):
    from radar.core.chat import ChatMessage, ChatSessionStore
    from radar.core.chat.events import new_id

    config = _config(tmp_path)
    store = ChatSessionStore.from_config(config)
    session = store.create_session(title="策略机会")
    store.append_message(
        session.session_id,
        ChatMessage(
            message_id=new_id(),
            role="user",
            content='查风华高科\n\n页面上下文：\n{"surface":"策略"}',
            created_at="2026-06-08T10:00:00",
        ),
    )
    store.append_message(
        session.session_id,
        ChatMessage(
            message_id=new_id(),
            role="tool",
            content='{"summary":"工具结果"}',
            created_at="2026-06-08T10:00:01",
        ),
    )

    client = TestClient(create_app(config))
    response = client.get(f"/api/chat/sessions/{session.session_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["session"]["session_id"] == session.session_id
    assert data["session"]["preview"] == "查风华高科"
    assert [message["content"] for message in data["messages"]] == ["查风华高科"]


def test_chat_session_detail_adds_turn_duration_to_assistant_messages(tmp_path):
    from radar.core.chat import ChatEvent, ChatMessage, ChatSessionStore
    from radar.core.chat.events import new_id

    config = _config(tmp_path)
    store = ChatSessionStore.from_config(config)
    session = store.create_session(title="耗时")
    user_message = ChatMessage(
        message_id=new_id(),
        role="user",
        content="看一下今天消息",
        created_at="2026-06-08T10:00:00",
    )
    assistant_message = ChatMessage(
        message_id=new_id(),
        role="assistant",
        content="先看半导体。",
        created_at="2026-06-08T10:00:04",
    )
    store.append_message(session.session_id, user_message)
    store.append_event(
        ChatEvent(
            event_id=new_id(),
            session_id=session.session_id,
            type="turn_started",
            created_at="2026-06-08T10:00:00",
            payload={"user_message_id": user_message.message_id},
        )
    )
    store.append_message(session.session_id, assistant_message)
    store.append_event(
        ChatEvent(
            event_id=new_id(),
            session_id=session.session_id,
            type="turn_completed",
            created_at="2026-06-08T10:00:04.250000",
            payload={
                "user_message_id": user_message.message_id,
                "assistant_message_id": assistant_message.message_id,
            },
        )
    )

    client = TestClient(create_app(config))
    response = client.get(f"/api/chat/sessions/{session.session_id}")

    assert response.status_code == 200
    messages = response.json()["messages"]
    assert [message["content"] for message in messages] == ["看一下今天消息", "先看半导体。"]
    assert messages[1]["metadata"]["duration_ms"] == 4250


def test_chat_session_detail_marks_interrupted_turn_continuable(tmp_path):
    from radar.core.chat import ChatEvent, ChatMessage, ChatSessionStore
    from radar.core.chat.events import new_id, now_iso

    config = _config(tmp_path)
    store = ChatSessionStore.from_config(config)
    session = store.create_session(title="洞察", metadata={"surface": "洞察"})
    user_message = ChatMessage(
        message_id=new_id(),
        role="user",
        content="我的个股证据链策略前 5 个",
        created_at="2026-06-08T10:00:00",
    )
    store.append_message(session.session_id, user_message)
    store.append_event(
        ChatEvent(
            event_id=new_id(),
            session_id=session.session_id,
            type="turn_started",
            created_at=now_iso(),
            payload={"user_message_id": user_message.message_id},
        )
    )
    store.append_message(
        session.session_id,
        ChatMessage(
            message_id=new_id(),
            role="tool",
            content='{"items":[{"ts_code":"002371.SZ"}]}',
            created_at="2026-06-08T10:00:01",
        ),
    )

    client = TestClient(create_app(config))
    response = client.get(f"/api/chat/sessions/{session.session_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["session"]["can_continue"] is True
    assert [message["content"] for message in data["messages"]] == ["我的个股证据链策略前 5 个"]


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


def test_organize_aggregate_endpoints_are_removed(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    assert client.get("/api/organize/aggregates").status_code == 404
    assert client.get("/api/organize/aggregates/evidence", params={"run_id": "r", "theme_index": 0}).status_code == 404


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
                "provider-a": {
                    "protocol": "openai",
                    "secret_ref": "a",
                    "model": "model-a",
                },
                "provider-b": {
                    "protocol": "anthropic",
                    "secret_ref": "b",
                    "model": "model-b",
                },
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


def test_anchor_jobs_endpoint_updates_market_anchors_and_reuses_running_job(monkeypatch, tmp_path):
    config = _config(tmp_path)
    calls: list[dict] = []
    started = Event()
    release = Event()

    def fake_ensure(config, *, trade_date, min_anchor_count, force):
        calls.append(
            {
                "trade_date": trade_date,
                "min_anchor_count": min_anchor_count,
                "force": force,
            }
        )
        started.set()
        release.wait(timeout=2)
        return SimpleNamespace(
            trade_date=trade_date,
            refreshed=True,
            anchor_count=3020,
            member_count=9000,
            skipped_reason=None,
            source_counts={},
            failed_sources={},
        )

    monkeypatch.setattr("radar.web.server.market_anchor_jobs.ensure_market_anchors", fake_ensure)

    client = TestClient(create_app(config))
    payload = {
        "trade_date": "20260604",
        "force": True,
        "min_anchor_count": 120,
    }
    response = client.post("/api/market/anchors/jobs", json=payload)

    assert response.status_code == 200
    first = response.json()["items"][0]
    assert started.wait(timeout=1)
    assert first["job_type"] == "anchor"
    assert first["status"] == "running"
    assert first["reused_existing"] is False
    assert get_run(config.database_path, first["run_id"]) is not None

    response = client.post("/api/market/anchors/jobs", json=payload)
    second = response.json()["items"][0]

    assert second["run_id"] == first["run_id"]
    assert second["reused_existing"] is True
    release.set()
    wait_for_run_status(config.database_path, first["run_id"], "succeeded")
    assert calls[0] == {
        "trade_date": "20260604",
        "min_anchor_count": 120,
        "force": True,
    }


def test_anchor_jobs_endpoint_records_resolved_trade_date(monkeypatch, tmp_path):
    config = _config(tmp_path)
    derivative_calls: list[Path] = []
    theme_calls: list[Path] = []
    monkeypatch.setattr(
        "radar.web.server.market_anchor_jobs.ensure_market_anchors",
        lambda *args, **kwargs: SimpleNamespace(
            trade_date="20260605",
            refreshed=False,
            anchor_count=3020,
            member_count=9000,
            skipped_reason="20260606 非交易日，使用最近交易日 20260605 的 anchor 词库",
            source_counts={},
            failed_sources={},
        ),
    )
    monkeypatch.setattr(
        "radar.web.server.market_anchor_jobs.refresh_market_anchor_derivatives",
        lambda config: derivative_calls.append(config.market_database_path)
        or SimpleNamespace(latest_trade_date="20260605", current_count=10, span_count=8),
    )
    monkeypatch.setattr(
        "radar.web.server.market_anchor_jobs.refresh_market_theme_normalization",
        lambda config, *, rebuild_anchor_derivatives=True: theme_calls.append(config.market_database_path)
        or SimpleNamespace(
            latest_trade_date="20260605",
            theme_count=5,
            source_link_count=8,
            membership_count=12,
            current_stock_count=10,
            covered_stock_count=9,
            coverage_ratio=0.9,
            ambiguous_stock_count=1,
        ),
    )

    client = TestClient(create_app(config))
    response = client.post(
        "/api/market/anchors/jobs",
        json={
            "trade_date": "20260606",
        },
    )

    assert response.status_code == 200
    run_id = response.json()["items"][0]["run_id"]
    wait_for_run_status(config.database_path, run_id, "skipped")
    run = get_run(config.database_path, run_id)
    assert run is not None
    assert run.metadata["trade_date"] == "20260605"
    assert run.metadata["derived_latest_trade_date"] == "20260605"
    assert run.metadata["derived_current_count"] == 10
    assert run.metadata["derived_span_count"] == 8
    assert run.metadata["theme_count"] == 5
    assert run.metadata["theme_membership_count"] == 12
    assert run.metadata["theme_coverage_ratio"] == 0.9
    assert derivative_calls == [config.market_database_path]
    assert theme_calls == [config.market_database_path]


def test_aggregate_refine_endpoints_are_removed(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    assert client.post("/api/aggregate/refine/jobs", json={}).status_code == 404
    assert client.get("/api/aggregate/refine/results").status_code == 404


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


def test_stock_evidence_chain_job_uses_configured_provider_pool(monkeypatch, tmp_path):
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

    def fake_build(
        config,
        *,
        as_of,
        window_start,
        evidence_days,
        limit,
        run_llm,
        llm_workers,
        llm_providers,
        llm_model,
        force_llm,
    ):
        calls.append(
            {
                "as_of": as_of,
                "window_start": window_start,
                "evidence_days": evidence_days,
                "limit": limit,
                "run_llm": run_llm,
                "llm_workers": llm_workers,
                "llm_providers": llm_providers,
                "llm_model": llm_model,
                "force_llm": force_llm,
            }
        )
        started.set()
        release.wait(timeout=2)
        return SimpleNamespace(
            as_of=as_of,
            window_start=window_start,
            evidence_start=as_of - timedelta(days=evidence_days),
            indexed_messages=10,
            mention_count=20,
            candidate_count=3,
            judged_count=3,
            reused_count=0,
            failed_count=0,
        )

    monkeypatch.setattr("radar.web.server.strategy_jobs.build_stock_evidence_chain", fake_build)

    client = TestClient(create_app(config))
    payload = {
        "start_time": "2026-06-04T15:00:00",
        "end_time": "2026-06-05T09:30:00",
        "evidence_days": 40,
        "limit": 120,
        "run_llm": True,
        "llm_workers": 16,
        "force_llm": False,
    }
    response = client.post("/api/strategy/evidence-chain/jobs", json=payload)

    assert response.status_code == 200
    first = response.json()["items"][0]
    assert started.wait(timeout=1)
    run = get_run(config.database_path, first["run_id"])
    assert run is not None
    assert run.metadata["effective_provider_names"] == ["provider-a", "provider-b"]
    assert "providers=provider-a,provider-b" in run.target

    response = client.post("/api/strategy/evidence-chain/jobs", json=payload)
    second = response.json()["items"][0]

    assert second["run_id"] == first["run_id"]
    assert second["reused_existing"] is True
    release.set()
    wait_for_run_status(config.database_path, first["run_id"], "succeeded")
    assert calls[0]["llm_providers"] == ["provider-a", "provider-b"]
    assert calls[0]["llm_workers"] == 16


def test_lifecycle_digest_job_uses_configured_provider_pool(monkeypatch, tmp_path):
    config = _config(
        tmp_path,
        llm={
            "providers": {
                "provider-a": {
                    "protocol": "openai",
                    "secret_ref": "a",
                    "model": "model-a",
                },
                "provider-b": {
                    "protocol": "anthropic",
                    "secret_ref": "b",
                    "model": "model-b",
                },
            }
        },
    )
    calls: list[dict] = []
    started = Event()
    release = Event()

    def fake_refresh(config, *, limit, force, provider_names, model, llm_workers):
        calls.append(
            {
                "limit": limit,
                "force": force,
                "provider_names": provider_names,
                "model": model,
                "llm_workers": llm_workers,
            }
        )
        started.set()
        release.wait(timeout=2)
        return SimpleNamespace(
            as_of_time=datetime.fromisoformat("2026-06-05T09:30:00"),
            scanned_count=120,
            processable_count=120,
            pending_count=120,
            generated_count=118,
            reused_count=0,
            skipped_count=0,
            failed_count=2,
            rerun_reason_counts={"缺少生命周期摘要": 120},
        )

    monkeypatch.setattr("radar.web.server.strategy_jobs.refresh_lifecycle_digests", fake_refresh)

    client = TestClient(create_app(config))
    payload = {
        "limit": 120,
        "force": False,
        "llm_workers": 16,
    }
    response = client.post("/api/strategy/lifecycle-digests/jobs", json=payload)

    assert response.status_code == 200
    first = response.json()["items"][0]
    assert started.wait(timeout=1)
    run = get_run(config.database_path, first["run_id"])
    assert run is not None
    assert run.metadata["effective_provider_names"] == ["provider-a", "provider-b"]
    assert "providers=provider-a,provider-b" in run.target

    response = client.post("/api/strategy/lifecycle-digests/jobs", json=payload)
    second = response.json()["items"][0]

    assert second["run_id"] == first["run_id"]
    assert second["reused_existing"] is True
    release.set()
    wait_for_run_status(config.database_path, first["run_id"], "succeeded")
    assert calls[0]["provider_names"] == ["provider-a", "provider-b"]
    assert calls[0]["llm_workers"] == 16


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
