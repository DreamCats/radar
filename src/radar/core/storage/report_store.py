from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote
from uuid import uuid4

from pydantic import BaseModel, Field

from radar.core.storage.db import SQLITE_TIMEOUT_SECONDS, configure_sqlite_connection, migrate_report_db
from radar.core.usecases.catalyst_valuation_report.models import (
    CatalystValuationReport,
    CatalystValuationReportRunResult,
)
from radar.core.usecases.catalyst_valuation_report.render import render_report_html


REPORT_KIND_CATALYST_VALUATION = "catalyst_valuation_report"
ReportStatus = Literal["succeeded", "skipped", "partial_failed", "failed"]
UpsideChatRunStatus = Literal["running", "completed", "failed", "cancelled"]


class CatalystValuationReportStockSummary(BaseModel):
    stock_key: str
    ts_code: str | None = None
    stock_name: str
    evidence_count: int
    latest_message_time: datetime


class ReportNotificationRecord(BaseModel):
    notification_id: str
    report_id: str
    channel: str
    status: Literal["succeeded", "failed"]
    sent_at: datetime
    error_message: str | None = None
    created_at: datetime


class CatalystValuationReportArchiveItem(BaseModel):
    report_id: str
    run_id: str | None = None
    kind: str
    status: ReportStatus
    generated_at: datetime
    start_time: datetime
    end_time: datetime
    granularity_minutes: int | None = None
    local_html_path: str
    published_url: str | None = None
    total_feed_items: int
    total_candidate_stocks: int
    total_stocks: int
    bark_sent_at: datetime | None = None
    bark_error: str | None = None
    upside_chat_run_id: str | None = None
    upside_chat_session_id: str | None = None
    upside_chat_status: UpsideChatRunStatus | None = None
    upside_chat_updated_at: datetime | None = None
    upside_chat_error: str | None = None
    top_stocks: list[CatalystValuationReportStockSummary] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CatalystValuationReportArchiveDetail(CatalystValuationReportArchiveItem):
    request: dict[str, Any] = Field(default_factory=dict)
    report: CatalystValuationReport
    rendered_html: str
    notifications: list[ReportNotificationRecord] = Field(default_factory=list)


def save_catalyst_valuation_report(
    database: Path,
    *,
    request: dict[str, Any],
    result: CatalystValuationReportRunResult,
    run_id: str | None,
    status: ReportStatus,
) -> CatalystValuationReportArchiveDetail:
    report = result.report
    now = _now_text()
    report_id = _report_id_for_run(database, run_id) or f"cvr_{uuid4().hex}"
    rendered_html = render_report_html(report)
    request_json = _json(request)
    report_json = report.model_dump_json()
    granularity_minutes = _granularity_minutes(report)
    bark_sent_at = now if result.bark_sent else None
    bark_error = result.bark_error

    with _connect(database) as conn:
        conn.execute(
            """
            INSERT INTO catalyst_valuation_reports (
                report_id, run_id, kind, status, generated_at, window_start, window_end,
                granularity_minutes, local_html_path, published_url, total_feed_items,
                total_candidate_stocks, total_stocks, bark_sent_at, bark_error,
                request_json, report_json, rendered_html, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(report_id) DO UPDATE SET
                run_id = excluded.run_id,
                kind = excluded.kind,
                status = excluded.status,
                generated_at = excluded.generated_at,
                window_start = excluded.window_start,
                window_end = excluded.window_end,
                granularity_minutes = excluded.granularity_minutes,
                local_html_path = excluded.local_html_path,
                published_url = excluded.published_url,
                total_feed_items = excluded.total_feed_items,
                total_candidate_stocks = excluded.total_candidate_stocks,
                total_stocks = excluded.total_stocks,
                bark_sent_at = excluded.bark_sent_at,
                bark_error = excluded.bark_error,
                request_json = excluded.request_json,
                report_json = excluded.report_json,
                rendered_html = excluded.rendered_html,
                updated_at = excluded.updated_at
            """,
            (
                report_id,
                run_id,
                REPORT_KIND_CATALYST_VALUATION,
                status,
                report.generated_at.isoformat(),
                report.start_time.isoformat(),
                report.end_time.isoformat(),
                granularity_minutes,
                str(result.local_html_path),
                result.published_url,
                report.total_feed_items,
                report.total_candidate_stocks,
                report.total_stocks,
                bark_sent_at,
                bark_error,
                request_json,
                report_json,
                rendered_html,
                now,
                now,
            ),
        )
    detail = get_catalyst_valuation_report(database, report_id)
    if detail is None:
        raise RuntimeError(f"报告归档写入后无法读取: {report_id}")
    return detail


def list_catalyst_valuation_reports(
    database: Path,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    granularity_minutes: int | None = None,
    limit: int = 50,
) -> list[CatalystValuationReportArchiveItem]:
    if limit < 1 or limit > 200:
        raise ValueError("limit 必须在 1 到 200 之间")
    if not database.exists():
        return []

    clauses = ["kind = ?"]
    params: list[object] = [REPORT_KIND_CATALYST_VALUATION]
    if start_time is not None:
        clauses.append("window_end > ?")
        params.append(start_time.isoformat())
    if end_time is not None:
        clauses.append("window_start < ?")
        params.append(end_time.isoformat())
    if granularity_minutes is not None:
        clauses.append("granularity_minutes = ?")
        params.append(granularity_minutes)
    params.append(limit)

    with _connect_readonly(database) as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM catalyst_valuation_reports
            WHERE {" AND ".join(clauses)}
            ORDER BY generated_at DESC, created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [_row_to_item(row) for row in rows]


def get_catalyst_valuation_report(
    database: Path,
    report_id: str,
) -> CatalystValuationReportArchiveDetail | None:
    if not database.exists():
        return None
    with _connect_readonly(database) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM catalyst_valuation_reports
            WHERE report_id = ? AND kind = ?
            """,
            (report_id, REPORT_KIND_CATALYST_VALUATION),
        ).fetchone()
        if row is None:
            return None
        notifications = conn.execute(
            """
            SELECT *
            FROM report_notifications
            WHERE report_id = ?
            ORDER BY sent_at DESC
            """,
            (report_id,),
        ).fetchall()
    return _row_to_detail(row, notifications)


def record_report_notification(
    database: Path,
    *,
    report_id: str,
    channel: str,
    status: Literal["succeeded", "failed"],
    error_message: str | None = None,
) -> ReportNotificationRecord:
    now = _now_text()
    notification_id = f"rnf_{uuid4().hex}"
    with _connect(database) as conn:
        conn.execute(
            """
            INSERT INTO report_notifications (
                notification_id, report_id, channel, status, sent_at, error_message, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (notification_id, report_id, channel, status, now, error_message, now),
        )
        if status == "succeeded":
            conn.execute(
                """
                UPDATE catalyst_valuation_reports
                SET bark_sent_at = ?, bark_error = NULL, updated_at = ?
                WHERE report_id = ?
                """,
                (now, now, report_id),
            )
        else:
            conn.execute(
                """
                UPDATE catalyst_valuation_reports
                SET bark_error = ?, updated_at = ?
                WHERE report_id = ?
                """,
                (error_message, now, report_id),
            )
    return ReportNotificationRecord(
        notification_id=notification_id,
        report_id=report_id,
        channel=channel,
        status=status,
        sent_at=datetime.fromisoformat(now),
        error_message=error_message,
        created_at=datetime.fromisoformat(now),
    )


def _connect(database: Path) -> sqlite3.Connection:
    database.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database, timeout=SQLITE_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    configure_sqlite_connection(conn)
    migrate_report_db(conn)
    return conn


def _connect_readonly(database: Path) -> sqlite3.Connection:
    uri_path = quote(database.resolve().as_posix(), safe="/")
    conn = sqlite3.connect(f"file:{uri_path}?mode=ro", uri=True, timeout=SQLITE_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    configure_sqlite_connection(conn, enable_wal=False)
    conn.execute("PRAGMA query_only = ON")
    return conn


def _report_id_for_run(database: Path, run_id: str | None) -> str | None:
    if run_id is None or not database.exists():
        return None
    with _connect(database) as conn:
        row = conn.execute(
            "SELECT report_id FROM catalyst_valuation_reports WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    return str(row["report_id"]) if row is not None else None


def _row_to_item(row: sqlite3.Row) -> CatalystValuationReportArchiveItem:
    report = CatalystValuationReport.model_validate_json(row["report_json"])
    return CatalystValuationReportArchiveItem(
        report_id=row["report_id"],
        run_id=row["run_id"],
        kind=row["kind"],
        status=row["status"],
        generated_at=datetime.fromisoformat(row["generated_at"]),
        start_time=datetime.fromisoformat(row["window_start"]),
        end_time=datetime.fromisoformat(row["window_end"]),
        granularity_minutes=row["granularity_minutes"],
        local_html_path=row["local_html_path"],
        published_url=row["published_url"],
        total_feed_items=row["total_feed_items"],
        total_candidate_stocks=row["total_candidate_stocks"],
        total_stocks=row["total_stocks"],
        bark_sent_at=_parse_datetime(row["bark_sent_at"]),
        bark_error=row["bark_error"],
        top_stocks=[
            CatalystValuationReportStockSummary(
                stock_key=stock.stock_key,
                ts_code=stock.ts_code,
                stock_name=stock.stock_name,
                evidence_count=len(stock.evidence),
                latest_message_time=stock.latest_message_time,
            )
            for stock in report.stocks[:5]
        ],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _row_to_detail(
    row: sqlite3.Row,
    notification_rows: list[sqlite3.Row],
) -> CatalystValuationReportArchiveDetail:
    item = _row_to_item(row)
    return CatalystValuationReportArchiveDetail(
        **item.model_dump(),
        request=json.loads(row["request_json"]),
        report=CatalystValuationReport.model_validate_json(row["report_json"]),
        rendered_html=row["rendered_html"],
        notifications=[_row_to_notification(notification) for notification in notification_rows],
    )


def _row_to_notification(row: sqlite3.Row) -> ReportNotificationRecord:
    return ReportNotificationRecord(
        notification_id=row["notification_id"],
        report_id=row["report_id"],
        channel=row["channel"],
        status=row["status"],
        sent_at=datetime.fromisoformat(row["sent_at"]),
        error_message=row["error_message"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _granularity_minutes(report: CatalystValuationReport) -> int | None:
    seconds = (report.end_time - report.start_time).total_seconds()
    if seconds <= 0:
        return None
    return max(1, round(seconds / 60))


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)


def _now_text() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
