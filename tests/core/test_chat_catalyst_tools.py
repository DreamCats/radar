from __future__ import annotations

from datetime import datetime

from radar.core.chat import ChatAgent, ChatSessionStore
from radar.core.config import RadarConfig
from radar.core.messages import CatalystCategory, CatalystTermLibrary, save_catalyst_terms
from radar.core.models import RawMessage
from radar.core.storage import connect, init_db, upsert_messages


def test_builtin_catalyst_tools_read_terms_and_scan_local_database(tmp_path):
    config = RadarConfig(config_dir=tmp_path, storage={"data_dir": tmp_path / "data"})
    save_catalyst_terms(
        config,
        CatalystTermLibrary(
            categories=[
                CatalystCategory(id="order", name="订单", color="#0ecb81", terms=["新签订单"]),
                CatalystCategory(id="price", name="价格", color="#f5d547", terms=["涨价"]),
            ]
        ),
    )
    conn = connect(config.database_path)
    try:
        init_db(conn)
        upsert_messages(
            conn,
            [
                _message("m1", "2026-06-23T09:20:00", "东财策略", "AI 液冷 新签订单 300503"),
                _message("m2", "2026-06-23T09:30:00", "最强科技", "AI液冷，新签订单 300503"),
                _message("m3", "2026-06-23T10:00:00", "普通群", "普通聊天"),
                _message("m4", "2026-06-23T10:20:00", "涨价群", "电子布涨价"),
            ],
        )
    finally:
        conn.close()

    agent = ChatAgent(config, store=ChatSessionStore(tmp_path / "chat"))
    terms_result = agent.tools.get("radar_list_catalyst_terms").execute({})
    scan_result = agent.tools.get("radar_scan_catalysts").execute(
        {
            "start_time": "2026-06-23T09:00:00",
            "end_time": "2026-06-23T11:00:00",
            "category_ids": ["order"],
            "keyword": "新签订单",
            "limit": 5,
        }
    )

    assert [category["id"] for category in terms_result["categories"]] == ["order", "price"]
    assert scan_result["summary"]["total_items"] == 1
    assert scan_result["summary"]["available_total_items"] == 1
    assert scan_result["summary"]["total_messages"] == 2
    assert scan_result["items"][0]["message_id"] == "m1"
    assert scan_result["items"][0]["duplicate_count"] == 2
    assert [hit["term"] for hit in scan_result["items"][0]["matched_terms"]] == ["新签订单"]
    assert scan_result["items"][0]["stock_mentions"][0]["ts_code"] == "300503.SZ"


def _message(message_id: str, message_time: str, group_name: str, content: str) -> RawMessage:
    return RawMessage(
        message_id=message_id,
        source="个人群",
        sender="tester",
        message_time=datetime.fromisoformat(message_time),
        raw_content=content,
        group_name=group_name,
        fetch_time=datetime.fromisoformat("2026-06-23T10:00:00"),
        fetch_window="20260623090000-20260623110000",
    )
