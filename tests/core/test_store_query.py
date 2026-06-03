from __future__ import annotations

from datetime import datetime

from radar.core.models import RawMessage
from radar.core.query import MessageFilters, list_messages
from radar.core.store import init_db, upsert_messages


def test_upsert_and_cursor_query(sqlite_conn):
    init_db(sqlite_conn)
    messages = [
        _message("m1", "2026-06-04T10:00:00", "东财策略", "AI 算力观点"),
        _message("m2", "2026-06-04T09:00:00", "最强科技", "固态电池"),
    ]

    assert upsert_messages(sqlite_conn, messages) == 2
    assert upsert_messages(sqlite_conn, messages) == 0

    page = list_messages(sqlite_conn, MessageFilters(limit=1))

    assert [item.message_id for item in page.items] == ["m1"]
    assert page.next_cursor_id == "m1"


def test_keyword_search(sqlite_conn):
    init_db(sqlite_conn)
    upsert_messages(
        sqlite_conn,
        [
            _message("m1", "2026-06-04T10:00:00", "东财策略", "AI 算力观点"),
            _message("m2", "2026-06-04T09:00:00", "最强科技", "固态电池"),
        ],
    )

    page = list_messages(sqlite_conn, MessageFilters(keyword="固态", limit=10))

    assert [item.message_id for item in page.items] == ["m2"]


def _message(message_id: str, message_time: str, group_name: str, content: str) -> RawMessage:
    return RawMessage(
        message_id=message_id,
        source="个人群",
        sender="tester",
        message_time=datetime.fromisoformat(message_time),
        raw_content=content,
        group_name=group_name,
        fetch_time=datetime.fromisoformat("2026-06-04T11:00:00"),
        fetch_window="20260604090000-20260604110000",
    )
