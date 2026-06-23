from __future__ import annotations

from datetime import datetime

from radar.core.models import RawMessage
from radar.core.messages import (
    CatalystCategory,
    CatalystFeedFilters,
    CatalystTermLibrary,
    MessageFilters,
    get_message_context,
    get_message_overview,
    list_catalyst_feed,
    list_message_groups,
    list_messages,
)
from radar.core.storage import (
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


def test_get_message_context_defaults_to_same_conversation(sqlite_conn):
    init_db(sqlite_conn)
    upsert_messages(
        sqlite_conn,
        [
            _message("m1", "2026-06-04T09:00:00", "东财策略", "前文"),
            _message("m2", "2026-06-04T09:01:00", "其他群", "不应混入"),
            _message("m3", "2026-06-04T09:02:00", "东财策略", "目标"),
            _message("m4", "2026-06-04T09:03:00", "东财策略", "后文"),
        ],
    )

    context = get_message_context(sqlite_conn, message_id="m3", radius=2)

    assert context is not None
    assert context.target.message_id == "m3"
    assert [item.message_id for item in context.before] == ["m1"]
    assert [item.message_id for item in context.after] == ["m4"]


def test_message_overview_aggregates_without_loading_messages(sqlite_conn):
    init_db(sqlite_conn)
    upsert_messages(
        sqlite_conn,
        [
            _message("m1", "2026-06-04T10:00:00", "东财策略", "AI 算力观点"),
            _message("m2", "2026-06-04T09:00:00", "最强科技", "固态电池"),
            _message("m3", "2026-06-02T08:00:00", "东财策略", "PCB"),
            _message(
                "m4",
                "2026-06-03T08:30:00",
                None,
                "私聊消息",
                source="个人消息",
                sender="friend",
            ),
        ],
    )

    overview = get_message_overview(sqlite_conn, days=3, top_limit=5)

    assert overview.summary.total_count == 4
    assert overview.summary.group_message_count == 3
    assert overview.summary.personal_message_count == 1
    assert overview.summary.group_count == 2
    assert [(item.date, item.total_count) for item in overview.date_buckets] == [
        ("2026-06-02", 1),
        ("2026-06-03", 1),
        ("2026-06-04", 2),
    ]
    assert [(item.source, item.count) for item in overview.source_breakdown] == [("个人群", 3), ("个人消息", 1)]
    assert [(item.group_name, item.count) for item in overview.top_groups] == [("东财策略", 2), ("最强科技", 1)]
    assert overview.hourly_buckets[8].count == 2


def test_catalyst_feed_matches_terms_and_dedupes_sources(sqlite_conn):
    init_db(sqlite_conn)
    upsert_messages(
        sqlite_conn,
        [
            _message("m1", "2026-06-23T09:20:00", "东财策略", "AI 液冷 新签订单 300503"),
            _message("m2", "2026-06-23T09:30:00", "最强科技", "AI液冷，新签订单 300503"),
            _message("m3", "2026-06-23T10:00:00", "东财策略", "普通聊天"),
            _message("m4", "2026-06-23T10:30:00", "风险群", "客户砍单，需求不足"),
        ],
    )
    library = CatalystTermLibrary(
        categories=[
            CatalystCategory(id="order", name="订单", color="#0ecb81", terms=["新签订单"]),
            CatalystCategory(id="risk", name="风险", color="#8a8f98", terms=["砍单", "需求不足"]),
        ]
    )

    page = list_catalyst_feed(
        sqlite_conn,
        library,
        CatalystFeedFilters(
            start_time=datetime.fromisoformat("2026-06-23T09:00:00"),
            end_time=datetime.fromisoformat("2026-06-23T11:00:00"),
            limit=10,
        ),
    )

    assert page.summary.total_items == 2
    assert page.summary.total_messages == 3
    order_item = next(item for item in page.items if item.matched_terms[0].term == "新签订单")
    assert order_item.message_id == "m1"
    assert order_item.duplicate_count == 2
    assert [source.message_id for source in order_item.duplicate_sources] == ["m1", "m2"]
    assert [hit.term for hit in order_item.matched_terms] == ["新签订单"]
    assert order_item.stock_mentions[0].ts_code == "300503.SZ"


def test_catalyst_feed_category_filter_keeps_global_counts_and_all_hits(sqlite_conn):
    init_db(sqlite_conn)
    upsert_messages(
        sqlite_conn,
        [
            _message("m1", "2026-06-23T09:20:00", "东财策略", "AI 液冷 新签订单 涨价"),
            _message("m2", "2026-06-23T10:30:00", "风险群", "客户砍单，需求不足"),
        ],
    )
    library = CatalystTermLibrary(
        categories=[
            CatalystCategory(id="order", name="订单", color="#0ecb81", terms=["新签订单"]),
            CatalystCategory(id="price", name="价格", color="#f5d547", terms=["涨价"]),
            CatalystCategory(id="risk", name="风险", color="#8a8f98", terms=["砍单", "需求不足"]),
        ]
    )

    page = list_catalyst_feed(
        sqlite_conn,
        library,
        CatalystFeedFilters(
            start_time=datetime.fromisoformat("2026-06-23T09:00:00"),
            end_time=datetime.fromisoformat("2026-06-23T11:00:00"),
            category_ids=["order"],
            limit=10,
        ),
    )

    assert page.summary.total_items == 1
    assert page.summary.available_total_items == 2
    assert page.summary.category_counts == {"order": 1, "price": 1, "risk": 1}
    assert [hit.term for hit in page.items[0].matched_terms] == ["新签订单", "涨价"]


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


def _message(
    message_id: str,
    message_time: str,
    group_name: str | None,
    content: str,
    *,
    source: str = "个人群",
    sender: str = "tester",
) -> RawMessage:
    return RawMessage(
        message_id=message_id,
        source=source,
        sender=sender,
        message_time=datetime.fromisoformat(message_time),
        raw_content=content,
        group_name=group_name,
        fetch_time=datetime.fromisoformat("2026-06-04T11:00:00"),
        fetch_window="20260604090000-20260604110000",
    )
