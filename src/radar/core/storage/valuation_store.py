from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote
from uuid import uuid4

from pydantic import BaseModel, Field

from radar.core.storage.db import SQLITE_TIMEOUT_SECONDS, configure_sqlite_connection, migrate_valuation_db

ValuationParseStatus = Literal["ready", "missing_message", "missing_table", "failed"]
ValuationNotificationStatus = Literal["succeeded", "failed", "skipped"]


class ValuationMeasurementItemInput(BaseModel):
    rank: int | None = None
    ts_code: str | None = None
    name: str
    current_mv_text: str | None = None
    target_mv_text: str | None = None
    upside_text: str | None = None
    valuation_status: str | None = None
    confidence: str | None = None
    anchor_type: str | None = None
    evidence_level: str | None = None
    gap_reason: str | None = None
    notification_level: str | None = None
    key_validation: str | None = None
    risk_flags: str | None = None
    data_gaps: str | None = None
    is_positive: bool = False
    raw_row: dict[str, Any] = Field(default_factory=dict)


class ValuationMeasurementItem(ValuationMeasurementItemInput):
    item_id: str
    measurement_id: str
    row_order: int
    created_at: datetime


class ValuationMeasurement(BaseModel):
    measurement_id: str
    report_id: str
    chat_run_id: str
    session_id: str
    source_generated_at: datetime | None = None
    measured_at: datetime
    parse_status: ValuationParseStatus
    parse_error: str | None = None
    total_items: int
    positive_count: int
    published_url: str | None = None
    published_at: datetime | None = None
    publish_error: str | None = None
    notification_status: ValuationNotificationStatus | None = None
    notified_at: datetime | None = None
    notification_error: str | None = None
    created_at: datetime
    updated_at: datetime
    items: list[ValuationMeasurementItem] = Field(default_factory=list)


class ValuationMeasurementOpportunitySnapshot(BaseModel):
    measurement_id: str
    report_id: str
    chat_run_id: str
    session_id: str
    source_generated_at: datetime | None = None
    measured_at: datetime
    parse_status: ValuationParseStatus
    published_url: str | None = None
    notification_status: ValuationNotificationStatus | None = None
    notified_at: datetime | None = None
    item_id: str
    row_order: int
    rank: int | None = None
    ts_code: str | None = None
    name: str
    current_mv_text: str | None = None
    target_mv_text: str | None = None
    upside_text: str | None = None
    valuation_status: str | None = None
    confidence: str | None = None
    anchor_type: str | None = None
    evidence_level: str | None = None
    gap_reason: str | None = None
    notification_level: str | None = None
    key_validation: str | None = None
    risk_flags: str | None = None
    data_gaps: str | None = None
    is_positive: bool = False
    created_at: datetime


class ValuationMeasurementOpportunity(BaseModel):
    stock_key: str
    ts_code: str | None = None
    name: str
    latest: ValuationMeasurementOpportunitySnapshot
    history: list[ValuationMeasurementOpportunitySnapshot] = Field(default_factory=list)


def save_valuation_measurement(
    database: Path,
    *,
    report_id: str,
    chat_run_id: str,
    session_id: str,
    source_generated_at: datetime | None,
    measured_at: datetime | None,
    parse_status: ValuationParseStatus,
    parse_error: str | None,
    items: list[ValuationMeasurementItemInput],
) -> ValuationMeasurement:
    now = _now_text()
    measured = (measured_at or datetime.now(timezone.utc).astimezone()).isoformat()
    source_generated = source_generated_at.isoformat() if source_generated_at else None
    positive_count = sum(1 for item in items if item.is_positive)

    with _connect(database) as conn:
        row = conn.execute(
            "SELECT measurement_id FROM valuation_measurements WHERE chat_run_id = ?",
            (chat_run_id,),
        ).fetchone()
        measurement_id = str(row["measurement_id"]) if row is not None else f"vm_{uuid4().hex}"
        conn.execute(
            """
            INSERT INTO valuation_measurements (
                measurement_id, report_id, chat_run_id, session_id, source_generated_at,
                measured_at, parse_status, parse_error, total_items, positive_count,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_run_id) DO UPDATE SET
                report_id = excluded.report_id,
                session_id = excluded.session_id,
                source_generated_at = excluded.source_generated_at,
                measured_at = excluded.measured_at,
                parse_status = excluded.parse_status,
                parse_error = excluded.parse_error,
                total_items = excluded.total_items,
                positive_count = excluded.positive_count,
                updated_at = excluded.updated_at
            """,
            (
                measurement_id,
                report_id,
                chat_run_id,
                session_id,
                source_generated,
                measured,
                parse_status,
                parse_error,
                len(items),
                positive_count,
                now,
                now,
            ),
        )
        conn.execute("DELETE FROM valuation_measurement_items WHERE measurement_id = ?", (measurement_id,))
        for index, item in enumerate(items, start=1):
            conn.execute(
                """
                INSERT INTO valuation_measurement_items (
                    item_id, measurement_id, row_order, rank, ts_code, name,
                    current_mv_text, target_mv_text, upside_text, valuation_status,
                    confidence, anchor_type, evidence_level, gap_reason, notification_level,
                    key_validation, risk_flags, data_gaps, is_positive, raw_row_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"vmi_{uuid4().hex}",
                    measurement_id,
                    index,
                    item.rank,
                    item.ts_code,
                    item.name,
                    item.current_mv_text,
                    item.target_mv_text,
                    item.upside_text,
                    item.valuation_status,
                    item.confidence,
                    item.anchor_type,
                    item.evidence_level,
                    item.gap_reason,
                    item.notification_level,
                    item.key_validation,
                    item.risk_flags,
                    item.data_gaps,
                    1 if item.is_positive else 0,
                    _json(item.raw_row),
                    now,
                ),
            )
    measurement = get_valuation_measurement(database, measurement_id)
    if measurement is None:
        raise RuntimeError(f"估值测算结果写入后无法读取: {measurement_id}")
    return measurement


def get_valuation_measurement(database: Path, measurement_id: str) -> ValuationMeasurement | None:
    if not database.exists():
        return None
    with _connect_readonly(database) as conn:
        row = conn.execute(
            "SELECT * FROM valuation_measurements WHERE measurement_id = ?",
            (measurement_id,),
        ).fetchone()
        if row is None:
            return None
        item_rows = conn.execute(
            """
            SELECT * FROM valuation_measurement_items
            WHERE measurement_id = ?
            ORDER BY row_order ASC
            """,
            (measurement_id,),
        ).fetchall()
    return _row_to_measurement(row, item_rows)


def get_valuation_measurement_by_run(database: Path, chat_run_id: str) -> ValuationMeasurement | None:
    if not database.exists():
        return None
    with _connect_readonly(database) as conn:
        row = conn.execute(
            "SELECT measurement_id FROM valuation_measurements WHERE chat_run_id = ?",
            (chat_run_id,),
        ).fetchone()
    return get_valuation_measurement(database, str(row["measurement_id"])) if row is not None else None


def list_valuation_measurement_opportunities(
    database: Path,
    *,
    limit: int = 80,
    history_limit: int = 5,
) -> list[ValuationMeasurementOpportunity]:
    if limit < 1 or limit > 200:
        raise ValueError("limit 必须在 1 到 200 之间")
    if history_limit < 1 or history_limit > 20:
        raise ValueError("history_limit 必须在 1 到 20 之间")
    if not database.exists():
        return []

    with _connect_readonly(database) as conn:
        rows = conn.execute(
            """
            WITH joined AS (
                SELECT
                    COALESCE(NULLIF(i.ts_code, ''), i.name) AS stock_key,
                    m.measurement_id,
                    m.report_id,
                    m.chat_run_id,
                    m.session_id,
                    m.source_generated_at,
                    m.measured_at,
                    m.parse_status,
                    m.published_url,
                    m.notification_status,
                    m.notified_at,
                    i.item_id,
                    i.row_order,
                    i.rank,
                    i.ts_code,
                    i.name,
                    i.current_mv_text,
                    i.target_mv_text,
                    i.upside_text,
                    i.valuation_status,
                    i.confidence,
                    i.anchor_type,
                    i.evidence_level,
                    i.gap_reason,
                    i.notification_level,
                    i.key_validation,
                    i.risk_flags,
                    i.data_gaps,
                    i.is_positive,
                    i.created_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY COALESCE(NULLIF(i.ts_code, ''), i.name)
                        ORDER BY m.measured_at DESC, i.row_order ASC
                    ) AS history_rank
                FROM valuation_measurement_items i
                JOIN valuation_measurements m ON m.measurement_id = i.measurement_id
                WHERE m.parse_status = 'ready'
            )
            SELECT *
            FROM joined
            WHERE history_rank <= ?
            ORDER BY measured_at DESC, row_order ASC
            """,
            (history_limit,),
        ).fetchall()

    opportunities: dict[str, ValuationMeasurementOpportunity] = {}
    for row in rows:
        stock_key = str(row["stock_key"])
        if stock_key not in opportunities:
            latest = _row_to_opportunity_snapshot(row)
            opportunities[stock_key] = ValuationMeasurementOpportunity(
                stock_key=stock_key,
                ts_code=latest.ts_code,
                name=latest.name,
                latest=latest,
                history=[latest],
            )
            continue
        opportunities[stock_key].history.append(_row_to_opportunity_snapshot(row))

    return sorted(
        opportunities.values(),
        key=lambda item: (_opportunity_sort_rank(item.latest), -item.latest.measured_at.timestamp()),
    )[:limit]


def record_valuation_notification(
    database: Path,
    *,
    measurement_id: str,
    status: ValuationNotificationStatus,
    error_message: str | None = None,
) -> ValuationMeasurement:
    now = _now_text()
    with _connect(database) as conn:
        conn.execute(
            """
            UPDATE valuation_measurements
            SET notification_status = ?,
                notified_at = ?,
                notification_error = ?,
                updated_at = ?
            WHERE measurement_id = ?
            """,
            (status, now, error_message, now, measurement_id),
        )
    measurement = get_valuation_measurement(database, measurement_id)
    if measurement is None:
        raise RuntimeError(f"估值测算通知状态写入后无法读取: {measurement_id}")
    return measurement


def record_valuation_publication(
    database: Path,
    *,
    measurement_id: str,
    published_url: str | None = None,
    error_message: str | None = None,
) -> ValuationMeasurement:
    now = _now_text()
    with _connect(database) as conn:
        if published_url:
            conn.execute(
                """
                UPDATE valuation_measurements
                SET published_url = ?,
                    published_at = ?,
                    publish_error = NULL,
                    updated_at = ?
                WHERE measurement_id = ?
                """,
                (published_url, now, now, measurement_id),
            )
        else:
            conn.execute(
                """
                UPDATE valuation_measurements
                SET publish_error = ?,
                    updated_at = ?
                WHERE measurement_id = ?
                """,
                (error_message, now, measurement_id),
            )
    measurement = get_valuation_measurement(database, measurement_id)
    if measurement is None:
        raise RuntimeError(f"估值测算发布状态写入后无法读取: {measurement_id}")
    return measurement


def _connect(database: Path) -> sqlite3.Connection:
    database.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database, timeout=SQLITE_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    configure_sqlite_connection(conn)
    migrate_valuation_db(conn)
    return conn


def _connect_readonly(database: Path) -> sqlite3.Connection:
    uri_path = quote(database.resolve().as_posix(), safe="/")
    conn = sqlite3.connect(f"file:{uri_path}?mode=ro", uri=True, timeout=SQLITE_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    configure_sqlite_connection(conn, enable_wal=False)
    conn.execute("PRAGMA query_only = ON")
    return conn


def _row_to_measurement(row: sqlite3.Row, item_rows: list[sqlite3.Row]) -> ValuationMeasurement:
    return ValuationMeasurement(
        measurement_id=row["measurement_id"],
        report_id=row["report_id"],
        chat_run_id=row["chat_run_id"],
        session_id=row["session_id"],
        source_generated_at=_parse_datetime(row["source_generated_at"]),
        measured_at=datetime.fromisoformat(row["measured_at"]),
        parse_status=row["parse_status"],
        parse_error=row["parse_error"],
        total_items=row["total_items"],
        positive_count=row["positive_count"],
        published_url=row["published_url"],
        published_at=_parse_datetime(row["published_at"]),
        publish_error=row["publish_error"],
        notification_status=row["notification_status"],
        notified_at=_parse_datetime(row["notified_at"]),
        notification_error=row["notification_error"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        items=[_row_to_item(item_row) for item_row in item_rows],
    )


def _row_to_item(row: sqlite3.Row) -> ValuationMeasurementItem:
    return ValuationMeasurementItem(
        item_id=row["item_id"],
        measurement_id=row["measurement_id"],
        row_order=row["row_order"],
        rank=row["rank"],
        ts_code=row["ts_code"],
        name=row["name"],
        current_mv_text=row["current_mv_text"],
        target_mv_text=row["target_mv_text"],
        upside_text=row["upside_text"],
        valuation_status=row["valuation_status"],
        confidence=row["confidence"],
        anchor_type=_row_value(row, "anchor_type"),
        evidence_level=_row_value(row, "evidence_level"),
        gap_reason=_row_value(row, "gap_reason"),
        notification_level=_row_value(row, "notification_level"),
        key_validation=row["key_validation"],
        risk_flags=row["risk_flags"],
        data_gaps=row["data_gaps"],
        is_positive=bool(row["is_positive"]),
        raw_row=json.loads(row["raw_row_json"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_opportunity_snapshot(row: sqlite3.Row) -> ValuationMeasurementOpportunitySnapshot:
    return ValuationMeasurementOpportunitySnapshot(
        measurement_id=row["measurement_id"],
        report_id=row["report_id"],
        chat_run_id=row["chat_run_id"],
        session_id=row["session_id"],
        source_generated_at=_parse_datetime(row["source_generated_at"]),
        measured_at=datetime.fromisoformat(row["measured_at"]),
        parse_status=row["parse_status"],
        published_url=row["published_url"],
        notification_status=row["notification_status"],
        notified_at=_parse_datetime(row["notified_at"]),
        item_id=row["item_id"],
        row_order=row["row_order"],
        rank=row["rank"],
        ts_code=row["ts_code"],
        name=row["name"],
        current_mv_text=row["current_mv_text"],
        target_mv_text=row["target_mv_text"],
        upside_text=row["upside_text"],
        valuation_status=row["valuation_status"],
        confidence=row["confidence"],
        anchor_type=_row_value(row, "anchor_type"),
        evidence_level=_row_value(row, "evidence_level"),
        gap_reason=_row_value(row, "gap_reason"),
        notification_level=_row_value(row, "notification_level"),
        key_validation=row["key_validation"],
        risk_flags=row["risk_flags"],
        data_gaps=row["data_gaps"],
        is_positive=bool(row["is_positive"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _opportunity_sort_rank(snapshot: ValuationMeasurementOpportunitySnapshot) -> int:
    if snapshot.notification_level == "可通知" or snapshot.is_positive:
        return 0
    if snapshot.notification_level == "条件触发":
        return 1
    if snapshot.notification_level == "仅入库不通知":
        return 2
    return 3


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)


def _row_value(row: sqlite3.Row, key: str) -> str | None:
    return row[key] if key in row.keys() else None


def _now_text() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
