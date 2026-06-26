from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from radar.core.config import RadarConfig
from radar.core.models import RawMessage
from radar.core.storage import connect, init_db, upsert_messages
from radar.web.server.app import create_app


def test_messages_overview_endpoint_does_not_return_anchor_heat(tmp_path: Path):
    config = _config(tmp_path)
    messages = [
        _message("m1", "2026-06-04T10:00:00"),
        _message("m2", "2026-06-04T09:00:00"),
        _message("m3", "2026-05-20T09:00:00"),
    ]
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, messages)
    finally:
        conn.close()

    client = TestClient(create_app(config))
    response = client.get("/api/messages/overview", params={"days": 2})

    assert response.status_code == 200
    assert "anchor_heat" not in response.json()


def _config(tmp_path: Path) -> RadarConfig:
    return RadarConfig(storage={"data_dir": tmp_path / "data", "database": tmp_path / "radar.sqlite3"})


def _message(message_id: str, message_time: str) -> RawMessage:
    return RawMessage(
        message_id=message_id,
        source="个人群",
        sender="tester",
        message_time=datetime.fromisoformat(message_time),
        raw_content="人形机器人观点",
        group_name="东财策略",
        fetch_time=datetime.fromisoformat("2026-06-04T10:01:00"),
        fetch_window="20260604090000-20260604110000",
    )

