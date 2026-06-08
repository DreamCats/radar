from __future__ import annotations

from fastapi.testclient import TestClient

from radar.core.chat import ChatSessionStore
from radar.core.config import RadarConfig
from radar.web.server.app import create_app


def test_chat_session_delete_endpoint_removes_file_backed_session(tmp_path):
    config = RadarConfig(
        storage={
            "data_dir": tmp_path / "data",
            "database": tmp_path / "radar.sqlite3",
        }
    )
    store = ChatSessionStore.from_config(config)
    session = store.create_session(title="待删除")

    client = TestClient(create_app(config))
    response = client.delete(f"/api/chat/sessions/{session.session_id}")

    assert response.status_code == 204
    assert not store.session_dir(session.session_id).exists()
    assert client.get(f"/api/chat/sessions/{session.session_id}").status_code == 404
