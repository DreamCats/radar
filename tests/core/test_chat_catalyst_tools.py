from __future__ import annotations

from datetime import datetime

from radar.core.chat import ChatAgent, ChatSessionStore
from radar.core.config import RadarConfig
from radar.core.messages import CatalystCategory, CatalystTermLibrary, load_catalyst_terms, save_catalyst_terms
from radar.core.models import RawMessage
from radar.core.storage import connect, init_db, upsert_messages
from radar.core.storage.report_store import save_catalyst_valuation_report
from radar.core.usecases.catalyst_valuation_report.models import (
    CatalystValuationEvidence,
    CatalystValuationReport,
    CatalystValuationReportRunResult,
    CatalystValuationStockContext,
)


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


def test_default_catalyst_terms_exclude_low_signal_meeting_terms(tmp_path):
    config = RadarConfig(config_dir=tmp_path, storage={"data_dir": tmp_path / "data"})

    library = load_catalyst_terms(config)
    terms = {term for category in library.categories for term in category.terms}

    assert {"调研", "会议", "路演", "1v1", "一对一", "董秘", "IR", "继续推荐", "弹性"}.isdisjoint(terms)


def test_builtin_catalyst_tool_reads_valuation_report_by_id(tmp_path):
    config = RadarConfig(config_dir=tmp_path, storage={"data_dir": tmp_path / "data"})
    saved = save_catalyst_valuation_report(
        config.reports_database_path,
        request={"limit": 200, "publish": True},
        result=_valuation_result(tmp_path),
        run_id="run-cvr",
        status="succeeded",
    )
    agent = ChatAgent(config, store=ChatSessionStore(tmp_path / "chat"))

    result = agent.tools.get("radar_get_catalyst_valuation_report").execute(
        {
            "report_id": saved.report_id,
            "max_stocks": 1,
            "max_evidence_per_stock": 1,
            "include_rendered_html": True,
            "max_html_chars": 1200,
        }
    )
    missing = agent.tools.get("radar_get_catalyst_valuation_report").execute({"report_id": "missing"})

    assert result["found"] is True
    assert result["report_id"] == saved.report_id
    assert result["run_id"] == "run-cvr"
    assert result["published_url"] == "https://example.com/report.html"
    assert result["totals"] == {"feed_items": 5, "candidate_stocks": 2, "stocks": 1}
    assert result["stocks"][0]["stock_name"] == "胜宏科技"
    assert result["stocks"][0]["evidence"][0]["valuation_numbers"] == ["10 亿"]
    assert "Radar 催化估值线索报告" in result["rendered_html"]
    assert missing == {"found": False, "report_id": "missing"}


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


def _valuation_result(tmp_path) -> CatalystValuationReportRunResult:
    start_time = datetime.fromisoformat("2026-06-28T09:00:00")
    end_time = datetime.fromisoformat("2026-06-28T10:00:00")
    return CatalystValuationReportRunResult(
        report=CatalystValuationReport(
            generated_at=end_time,
            start_time=start_time,
            end_time=end_time,
            total_feed_items=5,
            total_candidate_stocks=2,
            total_stocks=1,
            stocks=[
                CatalystValuationStockContext(
                    stock_key="300476.SZ",
                    ts_code="300476.SZ",
                    stock_name="胜宏科技",
                    first_message_time=datetime.fromisoformat("2026-06-28T09:30:00"),
                    latest_message_time=datetime.fromisoformat("2026-06-28T09:40:00"),
                    evidence=[
                        CatalystValuationEvidence(
                            message_id="m-cvr-1",
                            source="个人群",
                            sender="tester",
                            group_name="东财策略",
                            message_time=datetime.fromisoformat("2026-06-28T09:30:00"),
                            latest_message_time=datetime.fromisoformat("2026-06-28T09:40:00"),
                            content="胜宏科技 新签订单 10 亿。",
                            matched_terms=["新签订单"],
                            valuation_terms=["订单"],
                            valuation_numbers=["10 亿"],
                        )
                    ],
                )
            ],
        ),
        local_html_path=tmp_path / "report.html",
        published_url="https://example.com/report.html",
    )
