from __future__ import annotations

from datetime import datetime

from radar.core.storage.report_store import (
    get_catalyst_valuation_report,
    list_catalyst_valuation_reports,
    record_report_notification,
    save_catalyst_valuation_report,
)
from radar.core.usecases.catalyst_valuation_report.models import (
    CatalystValuationEvidence,
    CatalystValuationReport,
    CatalystValuationReportRunResult,
    CatalystValuationStockContext,
)


def test_report_store_saves_and_reads_catalyst_valuation_report(tmp_path):
    database = tmp_path / "reports.sqlite3"
    result = _result(tmp_path)

    saved = save_catalyst_valuation_report(
        database,
        request={"limit": 200, "publish": True, "notify": False},
        result=result,
        run_id="run-catalyst",
        status="succeeded",
    )

    assert saved.run_id == "run-catalyst"
    assert saved.granularity_minutes == 60
    assert saved.published_url == "https://example.com/report.html"
    assert saved.report.stocks[0].stock_name == "胜宏科技"
    assert "Radar 催化估值线索报告" in saved.rendered_html

    items = list_catalyst_valuation_reports(
        database,
        start_time=datetime.fromisoformat("2026-06-28T09:30:00"),
        end_time=datetime.fromisoformat("2026-06-28T10:30:00"),
        granularity_minutes=60,
    )

    assert [item.report_id for item in items] == [saved.report_id]
    assert items[0].top_stocks[0].stock_name == "胜宏科技"

    notification = record_report_notification(
        database,
        report_id=saved.report_id,
        channel="bark",
        status="succeeded",
    )
    detail = get_catalyst_valuation_report(database, saved.report_id)

    assert detail is not None
    assert detail.bark_sent_at == notification.sent_at
    assert detail.notifications[0].notification_id == notification.notification_id


def _result(tmp_path) -> CatalystValuationReportRunResult:
    start_time = datetime.fromisoformat("2026-06-28T09:00:00")
    end_time = datetime.fromisoformat("2026-06-28T10:00:00")
    report = CatalystValuationReport(
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
                        message_id="m1",
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
    )
    return CatalystValuationReportRunResult(
        report=report,
        local_html_path=tmp_path / "report.html",
        published_url="https://example.com/report.html",
    )
