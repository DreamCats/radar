from __future__ import annotations

from datetime import datetime

from radar.core.models import RawMessage
from radar.core.messages import MessageFilters, list_message_groups, list_messages
from radar.core.store import (
    fetch_window_covered,
    fetch_window_exists,
    init_db,
    record_fetch_window,
    upsert_messages,
)


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


def test_upsert_skips_duplicate_message_fingerprint(sqlite_conn):
    init_db(sqlite_conn)

    first = _message("m1", "2026-06-04T10:00:00", "东财策略", "AI 算力观点")
    duplicate = _message("m1-copy", "2026-06-04T10:00:00", "东财策略", "AI 算力观点")

    assert upsert_messages(sqlite_conn, [first, duplicate]) == 1
    page = list_messages(sqlite_conn, MessageFilters(limit=10))

    assert [item.message_id for item in page.items] == ["m1"]


def test_list_message_groups(sqlite_conn):
    init_db(sqlite_conn)
    upsert_messages(
        sqlite_conn,
        [
            _message("m1", "2026-06-04T10:00:00", "东财策略", "AI 算力观点"),
            _message("m2", "2026-06-04T09:00:00", "最强科技", "固态电池"),
            _message("m3", "2026-06-04T08:00:00", "东财策略", "PCB"),
        ],
    )

    groups = list_message_groups(sqlite_conn, source="个人群", limit=10)

    assert [(item.group_name, item.message_count) for item in groups] == [("东财策略", 2), ("最强科技", 1)]


def test_fetch_window_record(sqlite_conn):
    init_db(sqlite_conn)

    assert not fetch_window_exists(
        sqlite_conn,
        source="个人群",
        start_time="2026-06-04T09:00:00",
        end_time="2026-06-04T10:00:00",
    )

    record_fetch_window(
        sqlite_conn,
        source="个人群",
        start_time="2026-06-04T09:00:00",
        end_time="2026-06-04T10:00:00",
        fetched_at="2026-06-04T10:01:00",
        raw_count=2,
        stored_count=2,
        filtered_count=0,
    )

    assert fetch_window_exists(
        sqlite_conn,
        source="个人群",
        start_time="2026-06-04T09:00:00",
        end_time="2026-06-04T10:00:00",
    )


def test_fetch_window_covered_by_larger_window(sqlite_conn):
    init_db(sqlite_conn)
    record_fetch_window(
        sqlite_conn,
        source="个人群",
        start_time="2026-06-04T09:00:00",
        end_time="2026-06-04T12:00:00",
        fetched_at="2026-06-04T12:01:00",
        raw_count=6,
        stored_count=6,
        filtered_count=0,
    )

    assert fetch_window_covered(
        sqlite_conn,
        source="个人群",
        start_time="2026-06-04T10:00:00",
        end_time="2026-06-04T11:00:00",
    )
    assert not fetch_window_covered(
        sqlite_conn,
        source="个人群",
        start_time="2026-06-04T08:00:00",
        end_time="2026-06-04T10:00:00",
    )


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
