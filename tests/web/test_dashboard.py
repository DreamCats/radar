from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from radar.core.config import RadarConfig
from radar.core.models import RawMessage
from radar.core.store import connect, init_db, upsert_messages
from radar.web.server.app import create_app


def test_dashboard_summary_endpoint_writes_view_cache(tmp_path: Path):
    config = RadarConfig(storage={"data_dir": tmp_path / "data", "database": tmp_path / "radar.sqlite3"})
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(conn, [_message()])
    finally:
        conn.close()

    client = TestClient(create_app(config))
    response = client.get("/api/dashboard/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["overview"]["summary"]["total_count"] == 1
    assert data["runs"] == []

    conn = connect(config.database_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM view_cache WHERE cache_key LIKE 'dashboard.summary:%'"
        ).fetchone()
    finally:
        conn.close()
    assert row["count"] == 1


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
