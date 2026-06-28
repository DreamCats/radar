from __future__ import annotations

from datetime import datetime

from radar.core.models import RawMessage
from radar.core.messages import (
    CatalystCategory,
    CatalystFeedFilters,
    CatalystStockMention,
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
            _message("m4", "2026-06-23T10:30:00", "风险群", "300476 客户砍单，需求不足"),
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


def test_catalyst_feed_ignores_meeting_password_like_stock_code(sqlite_conn):
    init_db(sqlite_conn)
    upsert_messages(
        sqlite_conn,
        [
            _message("m1", "2026-06-23T09:20:00", "东财策略", "电话会议通知，密码：354817，扩产交流"),
            _message("m2", "2026-06-23T09:30:00", "东财策略", "利和兴 301013 扩产进展"),
        ],
    )
    library = CatalystTermLibrary(
        categories=[CatalystCategory(id="capacity", name="产能", color="#38bdf8", terms=["扩产"])]
    )

    page = list_catalyst_feed(
        sqlite_conn,
        library,
        CatalystFeedFilters(
            start_time=datetime.fromisoformat("2026-06-23T09:00:00"),
            end_time=datetime.fromisoformat("2026-06-23T10:00:00"),
            limit=10,
        ),
    )

    assert page.summary.total_items == 1
    assert page.items[0].message_id == "m2"
    assert [mention.ts_code for mention in page.items[0].stock_mentions] == ["301013.SZ"]


def test_catalyst_feed_category_filter_keeps_global_counts_and_all_hits(sqlite_conn):
    init_db(sqlite_conn)
    upsert_messages(
        sqlite_conn,
        [
            _message("m1", "2026-06-23T09:20:00", "东财策略", "300503 AI 液冷 新签订单 涨价"),
            _message("m2", "2026-06-23T10:30:00", "风险群", "300476 客户砍单，需求不足"),
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
    assert page.summary.term_counts == {
        "order": {"新签订单": 1},
        "price": {"涨价": 1},
        "risk": {"砍单": 1, "需求不足": 1},
    }
    assert [hit.term for hit in page.items[0].matched_terms] == ["新签订单", "涨价"]


def test_catalyst_feed_term_filter_keeps_base_term_counts(sqlite_conn):
    init_db(sqlite_conn)
    upsert_messages(
        sqlite_conn,
        [
            _message("m1", "2026-06-23T09:20:00", "东财策略", "300503 涨价 提价"),
            _message("m2", "2026-06-23T09:30:00", "东财策略", "300476 提价"),
            _message("m3", "2026-06-23T09:40:00", "东财策略", "300001 涨价"),
        ],
    )
    library = CatalystTermLibrary(
        categories=[
            CatalystCategory(id="price", name="价格", color="#f5d547", terms=["涨价", "提价"]),
        ]
    )

    page = list_catalyst_feed(
        sqlite_conn,
        library,
        CatalystFeedFilters(
            start_time=datetime.fromisoformat("2026-06-23T09:00:00"),
            end_time=datetime.fromisoformat("2026-06-23T10:00:00"),
            category_ids=["price"],
            term_category_id="price",
            term="提价",
            limit=10,
        ),
    )

    assert page.summary.total_items == 2
    assert page.summary.available_total_items == 3
    assert page.summary.category_counts == {"price": 3}
    assert page.summary.term_counts == {"price": {"提价": 2, "涨价": 2}}
    assert {item.message_id for item in page.items} == {"m1", "m2"}


def test_catalyst_feed_uses_stock_detector_for_named_mentions(sqlite_conn):
    init_db(sqlite_conn)
    upsert_messages(
        sqlite_conn,
        [_message("m1", "2026-06-23T09:20:00", "东财策略", "胜宏科技 300476 在手订单充足")],
    )
    library = CatalystTermLibrary(
        categories=[CatalystCategory(id="order", name="订单", color="#0ecb81", terms=["在手订单"])]
    )

    page = list_catalyst_feed(
        sqlite_conn,
        library,
        CatalystFeedFilters(
            start_time=datetime.fromisoformat("2026-06-23T09:00:00"),
            end_time=datetime.fromisoformat("2026-06-23T11:00:00"),
            limit=10,
        ),
        stock_detector=lambda _content: [CatalystStockMention(ts_code="300476.SZ", stock_name="胜宏科技")],
    )

    assert [mention.model_dump() for mention in page.items[0].stock_mentions] == [
        {"ts_code": "300476.SZ", "stock_name": "胜宏科技"}
    ]


def test_catalyst_feed_groups_consecutive_messages_from_same_sender(sqlite_conn):
    init_db(sqlite_conn)
    upsert_messages(
        sqlite_conn,
        [
            _message("m1", "2026-06-23T09:20:00", "东财策略", "长征十号乙 0到1 催化"),
            _message("m2", "2026-06-23T09:20:08", "东财策略", "商业航天上下文正文"),
            _message("m3", "2026-06-23T09:20:16", "东财策略", "商业航天深度报告合集"),
            _message("m4", "2026-06-23T09:21:00", "东财策略", "普通聊天"),
        ],
    )
    library = CatalystTermLibrary(
        categories=[
            CatalystCategory(id="trend", name="趋势", color="#14b8a6", terms=["0到1"]),
            CatalystCategory(id="institution", name="机构传播", color="#5e6ad2", terms=["深度报告"]),
        ]
    )

    page = list_catalyst_feed(
        sqlite_conn,
        library,
        CatalystFeedFilters(
            start_time=datetime.fromisoformat("2026-06-23T09:00:00"),
            end_time=datetime.fromisoformat("2026-06-23T10:00:00"),
            limit=10,
        ),
    )

    assert page.summary.total_items == 1
    assert page.summary.total_messages == 3
    assert page.summary.duplicate_messages == 2
    assert page.items[0].message_count == 3
    assert [message.message_id for message in page.items[0].messages] == ["m1", "m2", "m3"]
    assert [hit.term for hit in page.items[0].messages[0].matched_terms] == ["0到1"]
    assert page.items[0].messages[1].matched_terms == []
    assert [hit.term for hit in page.items[0].messages[2].matched_terms] == ["深度报告"]
    assert page.items[0].duplicate_count == 1
    assert [hit.term for hit in page.items[0].matched_terms] == ["0到1", "深度报告"]
    assert "长征十号乙" in page.items[0].raw_content
    assert "商业航天上下文正文" in page.items[0].raw_content
    assert "商业航天深度报告合集" in page.items[0].raw_content


def test_catalyst_feed_dedupes_repeated_clusters_when_message_order_differs(sqlite_conn):
    init_db(sqlite_conn)
    upsert_messages(
        sqlite_conn,
        [
            _message("m1", "2026-06-23T09:20:00", "群一", "长征十号乙 0到1 催化"),
            _message("m2", "2026-06-23T09:20:05", "群一", "商业航天深度报告合集"),
            _message("m3", "2026-06-23T09:21:00", "群二", "商业航天深度报告合集"),
            _message("m4", "2026-06-23T09:21:05", "群二", "长征十号乙 0到1 催化"),
        ],
    )
    library = CatalystTermLibrary(
        categories=[
            CatalystCategory(id="trend", name="趋势", color="#14b8a6", terms=["0到1"]),
            CatalystCategory(id="institution", name="机构传播", color="#5e6ad2", terms=["深度报告"]),
        ]
    )

    page = list_catalyst_feed(
        sqlite_conn,
        library,
        CatalystFeedFilters(
            start_time=datetime.fromisoformat("2026-06-23T09:00:00"),
            end_time=datetime.fromisoformat("2026-06-23T10:00:00"),
            limit=10,
        ),
    )

    assert page.summary.total_items == 1
    assert page.summary.total_messages == 4
    assert page.items[0].message_count == 2
    assert len(page.items[0].messages) == 2
    assert page.items[0].duplicate_count == 2
    assert [source.message_count for source in page.items[0].duplicate_sources] == [2, 2]


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
