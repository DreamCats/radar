from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from threading import Event
from time import sleep

from fastapi.testclient import TestClient

from radar.core.config import RadarConfig
from radar.core.messages import CatalystStockMention, CatalystTermHit
from radar.core.models import RawMessage
from radar.core.storage import finish_run, get_run, start_run
from radar.core.storage import connect, init_db, upsert_messages
from radar.core.usecases import IngestRangeResult
from radar.core.usecases.analyst_mentions import (
    AnalystMentionEvidenceItem,
    AnalystMentionEvidenceResult,
    AnalystMentionMessageEvidenceItem,
    AnalystMentionMessageEvidenceResult,
    AnalystMentionSummaryResult,
    AnalystMentionSummaryRow,
)
from radar.core.usecases.premarket_signal import (
    PremarketConceptRank,
    PremarketEvidence,
    PremarketSignalQuery,
    PremarketSignalResult,
    PremarketSignalSummary,
    PremarketStockRank,
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


def test_catalyst_terms_endpoint_reads_and_updates_personal_terms(tmp_path):
    config = _config(tmp_path, config_dir=tmp_path / "config")
    client = TestClient(create_app(config))

    response = client.get("/api/catalyst/terms")

    assert response.status_code == 200
    assert response.json()["categories"][0]["name"] == "机构传播"

    updated = {
        "version": 1,
        "categories": [
            {
                "id": "test",
                "name": "测试标签",
                "color": "#5e6ad2",
                "terms": ["涨价", "AI液冷", "涨价", "", "订单"],
            }
        ],
    }
    update_response = client.put("/api/catalyst/terms", json=updated)

    assert update_response.status_code == 200
    assert update_response.json()["categories"][0]["terms"] == ["涨价", "AI液冷", "订单"]
    reload_response = client.get("/api/catalyst/terms")
    assert reload_response.json()["categories"][0]["terms"] == ["涨价", "AI液冷", "订单"]
    assert (config.config_dir / "catalyst_terms.yaml").exists()


def test_catalyst_feed_endpoint_returns_deduped_matches(tmp_path):
    config = _config(tmp_path, config_dir=tmp_path / "config")
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(
            conn,
            [
                _message("m1", "2026-06-23T09:00:00", raw_content="AI液冷 新签订单 300503"),
                _message(
                    "m2",
                    "2026-06-23T09:05:00",
                    group_name="最强科技",
                    raw_content="AI液冷，新签订单 300503",
                ),
                _message("m3", "2026-06-23T10:00:00", raw_content="普通聊天"),
            ],
        )
    finally:
        conn.close()

    client = TestClient(create_app(config))
    response = client.get(
        "/api/catalyst/feed",
        params={
            "start_time": "2026-06-23T08:00:00",
            "end_time": "2026-06-23T11:00:00",
            "category_ids": "order_customer",
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total_items"] == 1
    assert data["items"][0]["duplicate_count"] == 2
    assert data["items"][0]["matched_terms"][0]["term"] == "新签订单"
    assert data["items"][0]["stock_mentions"][0]["ts_code"] == "300503.SZ"


def test_premarket_signals_returns_slim_payload_and_lazy_detail(monkeypatch, tmp_path):
    config = _config(tmp_path, config_dir=tmp_path / "config")
    _init_empty_db(config)
    calls: list[PremarketSignalQuery] = []

    def fake_build(*args, query: PremarketSignalQuery, **kwargs) -> PremarketSignalResult:
        calls.append(query)
        return _premarket_result(query)

    monkeypatch.setattr("radar.web.server.routers.premarket.build_premarket_signal", fake_build)

    client = TestClient(create_app(config))
    params = {
        "start_time": "2026-06-30T07:00:00",
        "end_time": "2026-06-30T09:25:00",
        "limit": 30,
    }
    response = client.get("/api/premarket/signals", params=params)

    assert response.status_code == 200
    data = response.json()
    assert data["top_concepts"][0]["concept_code"] == "C001"
    assert data["top_concepts"][0]["top_stocks"] == []
    assert data["top_concepts"][0]["catalyst_terms"] == []
    assert data["top_concepts"][0]["evidence"] == []

    detail_response = client.get("/api/premarket/signals/concepts/C001", params=params)

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["top_stocks"][0]["stock_name"] == "样本股份"
    assert detail["evidence"][0]["raw_content"] == "样本股份 新签订单"
    assert len(calls) == 1


def test_premarket_signals_full_returns_precompressed_json(monkeypatch, tmp_path):
    config = _config(tmp_path, config_dir=tmp_path / "config")
    _init_empty_db(config)

    def fake_build(*args, query: PremarketSignalQuery, **kwargs) -> PremarketSignalResult:
        return _premarket_result(query)

    monkeypatch.setattr("radar.web.server.routers.premarket.build_premarket_signal", fake_build)

    client = TestClient(create_app(config))
    response = client.get(
        "/api/premarket/signals/full",
        params={
            "start_time": "2026-06-30T07:00:00",
            "end_time": "2026-06-30T09:25:00",
            "limit": 30,
        },
        headers={"Accept-Encoding": "gzip"},
    )

    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    assert int(response.headers["content-length"]) > 0
    assert response.json()["top_concepts"][0]["top_stocks"][0]["stock_name"] == "样本股份"


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


def test_message_read_endpoints_use_readonly_connection(tmp_path, monkeypatch):
    config = _config(tmp_path)
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, [_message()])
    finally:
        conn.close()

    from radar.web.server.routers import messages as messages_router

    calls = []
    real_connect_readonly = messages_router.connect_readonly

    def fake_connect_readonly(database_path):
        calls.append(database_path)
        return real_connect_readonly(database_path)

    monkeypatch.setattr(messages_router, "connect_readonly", fake_connect_readonly)

    client = TestClient(create_app(config))
    response = client.get("/api/conversations", params={"source": "group_message"})

    assert response.status_code == 200
    assert calls == [config.database_path]


def test_auth_disabled_by_default(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    response = client.get("/api/auth/status")

    assert response.status_code == 200
    assert response.json() == {
        "auth_required": False,
        "authenticated": True,
        "username": None,
    }


def test_auth_enabled_gates_api_and_uses_bearer_token(tmp_path):
    config = _config(
        tmp_path,
        web={"auth": {"enabled": True}},
        secrets={
            "web": {
                "auth": {
                    "token": "secret",
                }
            }
        },
    )
    client = TestClient(create_app(config))

    assert client.get("/api/health").status_code == 401
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
    assert client.post("/api/auth/login", json={"token": "bad"}).status_code == 401

    login_response = client.post(
        "/api/auth/login",
        json={"token": "secret"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["authenticated"] is True

    assert client.get("/api/runs").status_code == 401
    auth_headers = {"Authorization": "Bearer secret"}
    assert client.get("/api/health", headers=auth_headers).status_code == 200
    assert client.get("/api/runs", headers=auth_headers).status_code == 200

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
            yield SimpleNamespace(
                type="assistant_delta",
                message=None,
                content="先看",
                event=None,
            )
            yield SimpleNamespace(
                type="tool_message",
                message=ChatMessage(
                    message_id="tool-1",
                    role="tool",
                    content="x" * 2000,
                    created_at="2026-06-08T10:00:01",
                    metadata={"tool_name": "radar_search_messages"},
                ),
                content=None,
                event=None,
            )
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
    assert "x" * 2000 not in response.text
    assert '"stream_content_omitted":true' in response.text
    assert captured["session_id"] == "session-stream-1"
    assert captured["content"] == "这个信号怎么看？"
    assert captured["provider_name"] == "deep"
    assert '"surface":"源头雷达"' in str(captured["llm_content"])


def test_chat_run_endpoint_streams_replayable_events(tmp_path, monkeypatch):
    from radar.core.chat import ChatSessionStore
    from radar.core.chat.events import ChatMessage

    captured: dict[str, object] = {}

    class FakeChatAgent:
        def __init__(self, config):
            self.config = config
            self.store = ChatSessionStore.from_config(config)

        def create_session(self, *, title=None, metadata=None):
            captured["title"] = title
            captured["metadata"] = metadata
            return self.store.create_session(title=title, metadata=metadata)

        def stream_turn(self, session_id, content, **kwargs):
            captured["session_id"] = session_id
            captured["content"] = content
            captured["llm_content"] = kwargs.get("llm_content")
            yield SimpleNamespace(
                type="user_message",
                message=ChatMessage(
                    message_id="user-run-1",
                    role="user",
                    content=content,
                    created_at="2026-06-08T10:00:00",
                ),
                content=None,
                event=None,
            )
            yield SimpleNamespace(
                type="assistant_candidate_delta",
                message=None,
                content="先看",
                event=None,
            )
            yield SimpleNamespace(
                type="assistant_candidate_commit",
                message=None,
                content="先看来源质量。",
                event=None,
            )
            yield SimpleNamespace(
                type="assistant_message",
                message=ChatMessage(
                    message_id="assistant-run-1",
                    role="assistant",
                    content="先看来源质量。",
                    created_at="2026-06-08T10:00:01",
                ),
                content=None,
                event=None,
            )

    monkeypatch.setattr("radar.web.server.routers.chat.ChatAgent", FakeChatAgent)
    monkeypatch.setattr("radar.web.server.chat_run_worker.ChatAgent", FakeChatAgent)
    client = TestClient(create_app(_config(tmp_path)))

    created = client.post(
        "/api/chat/runs",
        json={
            "title": "PCB",
            "content": "这个信号怎么看？",
            "context": {"surface": "源头雷达", "entity_id": "sig-1"},
            "metadata": {"surface": "源头雷达"},
        },
    )

    assert created.status_code == 200
    run = created.json()["run"]
    assert run["run_id"]
    assert run["session_id"]

    streamed = client.get(f"/api/chat/runs/{run['run_id']}/stream")

    assert streamed.status_code == 200
    assert "event: session" in streamed.text
    assert "event: user_message" in streamed.text
    assert "event: assistant_candidate_delta" in streamed.text
    assert "event: assistant_candidate_commit" in streamed.text
    assert '"sequence_number":1' in streamed.text
    assert '"content":"先看"' in streamed.text
    assert '"content":"先看来源质量。"' in streamed.text
    assert captured["title"] == "PCB"
    assert captured["content"] == "这个信号怎么看？"
    assert '"surface":"源头雷达"' in str(captured["llm_content"])

    replayed = client.get(f"/api/chat/runs/{run['run_id']}/stream?after_seq=1")

    assert replayed.status_code == 200
    assert "event: session" not in replayed.text
    assert "event: assistant_candidate_delta" in replayed.text
    assert "event: assistant_candidate_commit" in replayed.text


def test_chat_runs_endpoint_lists_run_records_with_metadata(tmp_path):
    from radar.core.chat import ChatRunStore, ChatSessionStore

    config = _config(tmp_path)
    session = ChatSessionStore.from_config(config).create_session(title="估值推演")
    run = ChatRunStore.from_config(config).create_run(
        session.session_id,
        metadata={"surface": "valuation", "entity_id": "002371.SZ", "title": "估值推演"},
        request={"content": "看一下估值"},
    )
    client = TestClient(create_app(config))

    listed = client.get("/api/chat/runs")
    detail = client.get(f"/api/chat/runs/{run.run_id}")

    assert listed.status_code == 200
    item = listed.json()["items"][0]
    assert item["run_id"] == run.run_id
    assert item["session_id"] == session.session_id
    assert item["display_title"] == "估值推演"
    assert item["display_subtitle"] == "valuation · 002371.SZ"
    assert item["metadata"] == {"surface": "valuation", "entity_id": "002371.SZ", "title": "估值推演"}
    assert "request" not in item
    assert detail.status_code == 200
    assert detail.json()["run"]["metadata"]["title"] == "估值推演"


def test_chat_runs_endpoint_derives_catalyst_display_from_stored_context(tmp_path):
    from radar.core.chat import ChatRunStore, ChatSessionStore

    config = _config(tmp_path)
    session = ChatSessionStore.from_config(config).create_session(title="原文证据")
    context = {
        "surface": "催化词",
        "entity_id": "7d22d1ab6d6e7283c2aaed934761fd7c54b03c70",
        "title": "原文证据",
        "subtitle": "国联民生计算机魔都汇 · 2026-06-24 14:47:44",
        "fields": [
            {"label": "会话", "value": "国联民生计算机魔都汇"},
            {"label": "发送人", "value": "陈安宇@国联民生计算机"},
            {"label": "命中词", "value": "机构传播 / 强推、产能 / 兑现"},
            {"label": "标的", "value": "云天励飞 688343.SH"},
        ],
    }
    run = ChatRunStore.from_config(config).create_run(
        session.session_id,
        metadata={"surface": "催化词", "entity_id": context["entity_id"], "title": "原文证据"},
        request={"llm_content": f"查询市场证明\n\n页面上下文：\n{json.dumps(context, ensure_ascii=False)}"},
    )
    client = TestClient(create_app(config))

    item = client.get(f"/api/chat/runs/{run.run_id}").json()["run"]

    assert item["display_title"] == "云天励飞 688343.SH · 原文证据"
    assert item["display_subtitle"] == "催化词 · 国联民生计算机魔都汇 · 机构传播 / 强推、产能 / 兑现"


def test_chat_runs_endpoint_derives_wechat_list_display_from_request_content(tmp_path):
    from radar.core.chat import ChatRunStore, ChatSessionStore

    config = _config(tmp_path)
    session = ChatSessionStore.from_config(config).create_session(title="微信会话")
    run = ChatRunStore.from_config(config).create_run(
        session.session_id,
        metadata={
            "surface": "微信会话",
            "entity_id": "wechat:list",
            "title": "微信会话",
            "subtitle": "40 个会话 · 可继续翻页",
        },
        request={
            "content": "先浏览最近微信会话列表，再按需要调用 radar_list_conversations / radar_search_messages，找出当前消息流里最值得继续研究的 3 条线索；每条都区分原文证据、推断和待验证项。"
        },
    )
    client = TestClient(create_app(config))

    item = client.get(f"/api/chat/runs/{run.run_id}").json()["run"]

    assert item["display_title"] == "微信消息线索扫描"
    assert item["display_subtitle"] == "微信会话 · 40 个会话 · 可继续翻页"


def test_chat_run_stream_restarts_running_run_from_sqlite(tmp_path, monkeypatch):
    from radar.core.chat import ChatRunStore, ChatSessionStore
    from radar.core.chat.events import ChatMessage

    captured: dict[str, object] = {}

    class FakeChatAgent:
        def __init__(self, config):
            self.config = config
            self.store = ChatSessionStore.from_config(config)

        def stream_turn(self, session_id, content, **kwargs):
            captured["session_id"] = session_id
            captured["content"] = content
            captured["llm_content"] = kwargs.get("llm_content")
            yield SimpleNamespace(
                type="assistant_delta",
                message=None,
                content="恢复中",
                event=None,
            )
            yield SimpleNamespace(
                type="assistant_message",
                message=ChatMessage(
                    message_id="assistant-recovered-1",
                    role="assistant",
                    content="已恢复。",
                    created_at="2026-06-08T10:00:01",
                ),
                content=None,
                event=None,
            )

    config = _config(tmp_path)
    session = ChatSessionStore.from_config(config).create_session(title="恢复测试")
    run_store = ChatRunStore.from_config(config)
    run = run_store.create_run(
        session.session_id,
        metadata={"surface": "洞察", "entity_id": "dashboard"},
        request={
            "content": "继续处理",
            "llm_content": "继续处理\n\n页面上下文：\n{}",
            "system_prompt": "system",
            "provider_name": None,
        },
    )
    run_store.append_event(run.run_id, "session", {"session_id": session.session_id})

    monkeypatch.setattr("radar.web.server.chat_run_worker.ChatAgent", FakeChatAgent)
    client = TestClient(create_app(config))

    response = client.get(f"/api/chat/runs/{run.run_id}/stream")

    assert response.status_code == 200
    assert "event: assistant_delta" in response.text
    assert '"content":"恢复中"' in response.text
    assert captured["session_id"] == session.session_id
    assert captured["content"] == "继续处理"
    assert captured["llm_content"] == "继续处理\n\n页面上下文：\n{}"


def test_chat_run_worker_skips_run_owned_by_another_lease(tmp_path, monkeypatch):
    from radar.core.chat import ChatRunStore, ChatSessionStore
    from radar.web.server.chat_run_worker import _execute_chat_run

    config = _config(tmp_path)
    session = ChatSessionStore.from_config(config).create_session(title="lease 测试")
    run_store = ChatRunStore.from_config(config)
    run = run_store.create_run(
        session.session_id,
        request={
            "content": "继续处理",
            "llm_content": "继续处理\n\n页面上下文：\n{}",
        },
    )
    run_store.claim_run(run.run_id, "worker-1", ttl_seconds=30)
    called = {"agent": False}

    class FakeChatAgent:
        def __init__(self, config):
            called["agent"] = True

    monkeypatch.setattr("radar.web.server.chat_run_worker.ChatAgent", FakeChatAgent)

    _execute_chat_run(run_id=run.run_id, config=config, owner="worker-2")

    current = run_store.get_run(run.run_id)
    assert called["agent"] is False
    assert current.status == "running"
    assert current.lease_owner == "worker-1"


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
        content="我的催化词线索前 5 个",
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
    assert [message["content"] for message in data["messages"]] == ["我的催化词线索前 5 个"]


def test_removed_feature_endpoints_return_404(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    assert client.get("/api/dashboard/summary").status_code == 404
    assert client.post("/api/classify/messages/jobs", json={}).status_code == 404
    assert client.get("/api/organize/classifications").status_code == 404
    assert client.get("/api/organize/classifications/evidence").status_code == 404
    assert client.get("/api/organize/aggregates").status_code == 404
    assert client.get("/api/organize/aggregates/evidence", params={"run_id": "r", "theme_index": 0}).status_code == 404
    assert client.post("/api/market/anchors/jobs", json={}).status_code == 404
    assert client.post("/api/strategy/evidence-chain/jobs", json={}).status_code == 404
    assert client.post("/api/strategy/lifecycle-digests/jobs", json={}).status_code == 404


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


def test_runs_endpoint_keeps_reads_side_effect_free(monkeypatch, tmp_path):
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
    assert item["status"] == "running"
    assert item["error_message"] is None


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


def test_ingest_jobs_endpoint_returns_503_when_run_store_is_busy(monkeypatch, tmp_path):
    config = _config(tmp_path)
    start_run(config.database_path, kind="wechat_ingest_range", target="bootstrap")
    monkeypatch.setattr("radar.web.server.ingest_jobs.SUBMIT_SQLITE_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr("radar.web.server.ingest_jobs.SUBMIT_SQLITE_BUSY_TIMEOUT_MS", 10)

    locker = sqlite3.connect(config.database_path, timeout=0.01)
    try:
        locker.execute("BEGIN EXCLUSIVE")
        client = TestClient(create_app(config))
        response = client.post(
            "/api/ingest/wechat/jobs",
            json={
                "source": "group_message",
                "start_time": "2026-06-03T00:00:00",
                "end_time": "2026-06-04T00:00:00",
                "force": False,
                "chunk_hours": 1,
                "concurrency": 4,
            },
        )
    finally:
        locker.rollback()
        locker.close()

    assert response.status_code == 503
    assert response.json()["detail"] == "数据库正在写入，请稍后再提交"


def test_aggregate_refine_endpoints_are_removed(tmp_path):
    client = TestClient(create_app(_config(tmp_path)))

    assert client.post("/api/aggregate/refine/jobs", json={}).status_code == 404
    assert client.get("/api/aggregate/refine/results").status_code == 404
    assert client.post("/api/recommendation/backtest/jobs", json={}).status_code == 404
    assert client.get("/api/recommendation/backtest/summary").status_code == 404


def test_analyst_backtest_jobs_endpoint_starts_and_reuses_running_job(monkeypatch, tmp_path):
    config = _config(tmp_path)
    calls: list[dict] = []
    started = Event()
    release = Event()

    def fake_backtest(
        config,
        *,
        as_of,
        lookback_days,
        start_time,
        end_time,
        windows,
        source,
        cooldown_trade_days,
        remote_price_fetch,
        benchmark_ts_code,
        run_id,
    ):
        calls.append(
            {
                "as_of": as_of,
                "lookback_days": lookback_days,
                "start_time": start_time,
                "end_time": end_time,
                "windows": windows,
                "source": source,
                "cooldown_trade_days": cooldown_trade_days,
                "remote_price_fetch": remote_price_fetch,
                "benchmark_ts_code": benchmark_ts_code,
                "run_id": run_id,
            }
        )
        started.set()
        release.wait(timeout=2)

    monkeypatch.setattr("radar.web.server.backtest_jobs.refresh_analyst_stock_mentions", fake_backtest)

    client = TestClient(create_app(config))
    payload = {
        "as_of": "2026-06-05",
        "lookback_days": 40,
        "start_time": "2026-04-27T00:00:00",
        "end_time": "2026-06-05T15:30:00",
        "windows": [1, 3, 5],
        "source": "group_message",
        "cooldown_trade_days": 5,
        "benchmark_ts_code": "000300.SH",
        "remote_price_fetch": True,
    }
    response = client.post("/api/analyst/backtest/jobs", json=payload)

    assert response.status_code == 200
    first = response.json()["items"][0]
    assert started.wait(timeout=1)
    assert first["job_type"] == "analyst_backtest"
    assert first["status"] == "running"
    assert first["reused_existing"] is False
    run = get_run(config.database_path, first["run_id"])
    assert run is not None
    assert run.metadata["extractor_version"] == "analyst-stock-mention-v1"

    response = client.post("/api/analyst/backtest/jobs", json=payload)
    second = response.json()["items"][0]

    assert second["run_id"] == first["run_id"]
    assert second["reused_existing"] is True
    release.set()
    assert calls[0]["source"] == "个人群"
    assert calls[0]["start_time"] == datetime.fromisoformat("2026-04-27T00:00:00")
    assert calls[0]["end_time"] == datetime.fromisoformat("2026-06-05T15:30:00")
    assert calls[0]["windows"] == [1, 3, 5]
    assert calls[0]["cooldown_trade_days"] == 5
    assert calls[0]["remote_price_fetch"] is True
    assert calls[0]["benchmark_ts_code"] == "000300.SH"
    assert calls[0]["run_id"] == first["run_id"]


def test_analyst_backtest_summary_endpoint_returns_rows(monkeypatch, tmp_path):
    config = _config(tmp_path)
    calls: list[dict] = []

    def fake_summary(config, *, start_time, end_time, windows, source, min_count, limit, include_broad_list):
        calls.append(
            {
                "start_time": start_time,
                "end_time": end_time,
                "windows": windows,
                "source": source,
                "min_count": min_count,
                "limit": limit,
                "include_broad_list": include_broad_list,
            }
        )
        return AnalystMentionSummaryResult(
            start_time=start_time,
            end_time=end_time,
            windows=windows,
            row_count=1,
            rows=[
                AnalystMentionSummaryRow(
                    analyst_id="analyst-1",
                    analyst_display_name="张三-分析师",
                    event_count=4,
                    latest_event_time=datetime.fromisoformat("2026-06-05T10:00:00"),
                    metrics={"sample_count_t5": 3, "positive_rate_t5": 1.0},
                )
            ],
        )

    monkeypatch.setattr("radar.web.server.routers.backtest.summarize_analyst_stock_mentions", fake_summary)

    client = TestClient(create_app(config))
    response = client.get(
        "/api/analyst/backtest/summary",
        params={
            "start_time": "2026-05-01T00:00:00",
            "end_time": "2026-06-06T00:00:00",
            "source": "group_message",
            "window": 5,
            "min_count": 3,
            "limit": 10,
            "include_broad_list": "false",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["row_count"] == 1
    assert data["rows"][0]["analyst_display_name"] == "张三-分析师"
    assert calls[0]["source"] == "个人群"
    assert calls[0]["windows"] == [5]
    assert calls[0]["min_count"] == 3
    assert calls[0]["limit"] == 10
    assert calls[0]["include_broad_list"] is False


def test_analyst_backtest_evidence_endpoint_returns_rows(monkeypatch, tmp_path):
    config = _config(tmp_path)
    calls: list[dict] = []

    def fake_evidence(
        config,
        *,
        start_time,
        end_time,
        window,
        analyst,
        ts_code,
        source,
        limit,
        include_broad_list,
    ):
        calls.append(
            {
                "start_time": start_time,
                "end_time": end_time,
                "window": window,
                "analyst": analyst,
                "ts_code": ts_code,
                "source": source,
                "limit": limit,
                "include_broad_list": include_broad_list,
            }
        )
        return AnalystMentionEvidenceResult(
            start_time=start_time,
            end_time=end_time,
            window_days=window,
            row_count=1,
            rows=[
                AnalystMentionEvidenceItem(
                    mention_id="mention-1",
                    message_id="m1",
                    analyst_id="analyst-1",
                    analyst_display_name="张三-分析师",
                    ts_code="600900.SH",
                    stock_name="长江电力",
                    message_time=datetime.fromisoformat("2026-06-05T10:00:00"),
                    evidence_snippet="继续关注长江电力",
                    stock_count_in_message=1,
                    quality_flags=(),
                    window_days=5,
                    status="succeeded",
                    return_rate=0.08,
                    excess_return_rate=0.03,
                )
            ],
        )

    monkeypatch.setattr("radar.web.server.routers.backtest.list_analyst_stock_mention_evidence", fake_evidence)

    client = TestClient(create_app(config))
    response = client.get(
        "/api/analyst/backtest/evidence",
        params={
            "start_time": "2026-05-01T00:00:00",
            "end_time": "2026-06-06T00:00:00",
            "window": 5,
            "analyst": "analyst-1",
            "ts_code": "600900.SH",
            "source": "group_message",
            "limit": 10,
            "include_broad_list": "false",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["row_count"] == 1
    assert data["rows"][0]["evidence_snippet"] == "继续关注长江电力"
    assert calls[0]["window"] == 5
    assert calls[0]["analyst"] == "analyst-1"
    assert calls[0]["ts_code"] == "600900.SH"
    assert calls[0]["source"] == "个人群"
    assert calls[0]["include_broad_list"] is False


def test_analyst_backtest_message_evidence_endpoint_returns_grouped_rows(monkeypatch, tmp_path):
    config = _config(tmp_path)
    calls: list[dict] = []

    def fake_message_evidence(
        config,
        *,
        start_time,
        end_time,
        window,
        analyst,
        source,
        limit,
        include_broad_list,
    ):
        calls.append(
            {
                "start_time": start_time,
                "end_time": end_time,
                "window": window,
                "analyst": analyst,
                "source": source,
                "limit": limit,
                "include_broad_list": include_broad_list,
            }
        )
        item = AnalystMentionEvidenceItem(
            mention_id="mention-1",
            message_id="m1",
            analyst_id="analyst-1",
            analyst_display_name="张三-分析师",
            ts_code="600900.SH",
            stock_name="长江电力",
            message_time=datetime.fromisoformat("2026-06-05T10:00:00"),
            evidence_snippet="继续关注长江电力",
            stock_count_in_message=1,
            quality_flags=(),
            window_days=5,
            status="succeeded",
            return_rate=0.08,
            excess_return_rate=0.03,
        )
        return AnalystMentionMessageEvidenceResult(
            start_time=start_time,
            end_time=end_time,
            window_days=window,
            row_count=1,
            rows=[
                AnalystMentionMessageEvidenceItem(
                    message_id="m1",
                    analyst_id="analyst-1",
                    analyst_display_name="张三-分析师",
                    message_time=datetime.fromisoformat("2026-06-05T10:00:00"),
                    raw_content="继续关注长江电力和国投电力",
                    stock_count=1,
                    mentioned_stock_count=2,
                    quality_flags=(),
                    window_days=5,
                    metrics={"avg_return": 0.08, "succeeded_count": 1},
                    items=[item],
                )
            ],
        )

    monkeypatch.setattr(
        "radar.web.server.routers.backtest.list_analyst_stock_mention_message_evidence",
        fake_message_evidence,
    )

    client = TestClient(create_app(config))
    response = client.get(
        "/api/analyst/backtest/message-evidence",
        params={
            "start_time": "2026-05-01T00:00:00",
            "end_time": "2026-06-06T00:00:00",
            "window": 5,
            "analyst": "analyst-1",
            "source": "group_message",
            "limit": 10,
            "include_broad_list": "false",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["row_count"] == 1
    assert data["rows"][0]["raw_content"] == "继续关注长江电力和国投电力"
    assert data["rows"][0]["items"][0]["stock_name"] == "长江电力"
    assert calls[0]["window"] == 5
    assert calls[0]["analyst"] == "analyst-1"
    assert calls[0]["source"] == "个人群"
    assert calls[0]["include_broad_list"] is False


def _config(tmp_path, **overrides) -> RadarConfig:
    return RadarConfig(
        storage={
            "data_dir": tmp_path / "data",
            "database": tmp_path / "radar.sqlite3",
        },
        **overrides,
    )


def _init_empty_db(config: RadarConfig) -> None:
    conn = connect(config.database_path)
    try:
        init_db(conn)
    finally:
        conn.close()


def _premarket_result(query: PremarketSignalQuery) -> PremarketSignalResult:
    term = CatalystTermHit(
        category_id="order_customer",
        category_name="订单 / 客户",
        color="#5e6ad2",
        term="新签订单",
    )
    stock = PremarketStockRank(
        ts_code="300001.SZ",
        stock_name="样本股份",
        mention_count=3,
        person_count=2,
        message_count=2,
        first_time=query.start_time,
        latest_time=query.end_time,
        catalyst_terms=[term],
    )
    evidence = PremarketEvidence(
        message_id="m-premarket-1",
        source="个人群",
        sender="tester",
        group_name="测试群",
        message_time=query.start_time,
        raw_content="样本股份 新签订单",
        matched_terms=[term],
        stock_mentions=[CatalystStockMention(ts_code="300001.SZ", stock_name="样本股份")],
    )
    concept = PremarketConceptRank(
        concept_code="C001",
        concept_name="样本概念",
        source="ths",
        score=12.5,
        velocity_score=1.0,
        early_mention_count=1,
        late_mention_count=2,
        stock_count=1,
        mention_count=3,
        person_count=2,
        message_count=2,
        top_stocks=[stock],
        catalyst_terms=[term],
        evidence=[evidence],
    )
    return PremarketSignalResult(
        query=query,
        summary=PremarketSignalSummary(
            start_time=query.start_time,
            end_time=query.end_time,
            messages_scanned=8,
            catalyst_items=2,
            stock_mentions=3,
            dedup_person_stock_mentions=2,
            concept_source="ths",
            concept_count=1,
            ranked_concept_count=1,
        ),
        concepts=[concept],
        top_concepts=[concept],
        bottom_concepts=[concept],
        velocity_concepts=[concept],
    )


def _message(
    message_id: str = "m1",
    message_time: str = "2026-06-04T10:00:00",
    source: str = "个人群",
    group_name: str | None = "东财策略",
    *,
    sender: str = "tester",
    raw_content: str = "固态电池观点",
) -> RawMessage:
    return RawMessage(
        message_id=message_id,
        source=source,
        sender=sender,
        message_time=datetime.fromisoformat(message_time),
        raw_content=raw_content,
        group_name=group_name,
        fetch_time=datetime.fromisoformat("2026-06-04T10:01:00"),
        fetch_window="20260604090000-20260604110000",
    )
