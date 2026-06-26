from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from radar.core.config import RadarConfig
from radar.core.models import MessageSource
from radar.core.storage import connect, init_db
from radar.core.usecases.analyst_mentions.extract import stock_segment
from radar.core.usecases.analyst_mentions.models import (
    ANALYST_MENTION_EXTRACTOR_VERSION,
    DEFAULT_BENCHMARK_TS_CODE,
    AnalystMentionEvidenceItem,
    AnalystMentionEvidenceResult,
    AnalystMentionMessageEvidenceItem,
    AnalystMentionMessageEvidenceResult,
)


def list_analyst_stock_mention_evidence(
    config: RadarConfig,
    *,
    start_time: datetime,
    end_time: datetime,
    window: int = 5,
    analyst: str | None = None,
    ts_code: str | None = None,
    source: MessageSource | None = None,
    limit: int = 50,
    include_broad_list: bool = True,
    extractor_version: str = ANALYST_MENTION_EXTRACTOR_VERSION,
    benchmark_ts_code: str = DEFAULT_BENCHMARK_TS_CODE,
) -> AnalystMentionEvidenceResult:
    """列出有效提及的原文片段和对应 T+N 表现。"""

    _validate_inputs(start_time, end_time, window, limit)
    conn = connect(config.database_path)
    try:
        init_db(conn)
        rows = _rows(
            conn,
            start_time=start_time,
            end_time=end_time,
            window=window,
            analyst=analyst,
            ts_code=ts_code,
            source=source,
            limit=limit,
            include_broad_list=include_broad_list,
            extractor_version=extractor_version,
            benchmark_ts_code=benchmark_ts_code,
        )
    finally:
        conn.close()
    items = [_item(row, window=window) for row in rows]
    return AnalystMentionEvidenceResult(
        start_time=start_time,
        end_time=end_time,
        window_days=window,
        row_count=len(items),
        rows=items,
    )


def list_analyst_stock_mention_message_evidence(
    config: RadarConfig,
    *,
    start_time: datetime,
    end_time: datetime,
    window: int = 5,
    analyst: str | None = None,
    source: MessageSource | None = None,
    limit: int = 50,
    include_broad_list: bool = True,
    extractor_version: str = ANALYST_MENTION_EXTRACTOR_VERSION,
    benchmark_ts_code: str = DEFAULT_BENCHMARK_TS_CODE,
) -> AnalystMentionMessageEvidenceResult:
    """按原始消息聚合证据，保留完整叙事，再展示消息内股票表现。"""

    _validate_inputs(start_time, end_time, window, limit)
    conn = connect(config.database_path)
    try:
        init_db(conn)
        rows = _rows(
            conn,
            start_time=start_time,
            end_time=end_time,
            window=window,
            analyst=analyst,
            ts_code=None,
            source=source,
            limit=None,
            include_broad_list=include_broad_list,
            extractor_version=extractor_version,
            benchmark_ts_code=benchmark_ts_code,
        )
    finally:
        conn.close()
    grouped = _group_message_rows(rows, window=window)
    grouped.sort(key=lambda item: item.message_time, reverse=True)
    return AnalystMentionMessageEvidenceResult(
        start_time=start_time,
        end_time=end_time,
        window_days=window,
        row_count=len(grouped),
        rows=grouped[:limit],
    )


def _rows(
    conn: sqlite3.Connection,
    *,
    start_time: datetime,
    end_time: datetime,
    window: int,
    analyst: str | None,
    ts_code: str | None,
    source: MessageSource | None,
    limit: int | None,
    include_broad_list: bool,
    extractor_version: str,
    benchmark_ts_code: str,
) -> list[sqlite3.Row]:
    where = [
        "m.message_time >= ?",
        "m.message_time < ?",
        "m.extractor_version = ?",
        "m.is_effective = 1",
    ]
    if not include_broad_list:
        where.append("""m.quality_flags NOT LIKE '%"broad_list"%'""")
    params: list[Any] = [window, benchmark_ts_code]
    params.extend([start_time.isoformat(), end_time.isoformat(), extractor_version])
    if analyst:
        where.append("(m.analyst_display_name LIKE ? OR m.analyst_id = ?)")
        params.extend([f"%{analyst}%", analyst])
    if ts_code:
        where.append("m.ts_code = ?")
        params.append(ts_code)
    if source:
        where.append("m.source = ?")
        params.append(source)
    if limit is not None:
        params.append(limit)
        limit_clause = "LIMIT ?"
    else:
        limit_clause = ""
    return conn.execute(
        f"""
        SELECT
            m.mention_id, m.message_id, m.analyst_id, m.analyst_display_name,
            m.ts_code, m.stock_name, m.symbol, m.message_time, m.evidence_snippet,
            m.stock_count_in_message, m.quality_flags,
            msg.raw_content,
            w.status, w.target_trade_date, w.return_rate, w.positive, w.excess_return_rate
        FROM analyst_stock_mentions m
        JOIN messages msg ON msg.message_id = m.message_id
        LEFT JOIN analyst_stock_mention_windows w
          ON w.mention_id = m.mention_id
         AND w.window_days = ?
         AND w.benchmark_ts_code = ?
        WHERE {" AND ".join(where)}
        ORDER BY
            CASE WHEN w.status = 'succeeded' THEN 0 ELSE 1 END,
            w.return_rate DESC,
            m.message_time DESC
        {limit_clause}
        """,
        params,
    ).fetchall()


def _item(row: sqlite3.Row, *, window: int) -> AnalystMentionEvidenceItem:
    stock_name = str(row["stock_name"])
    ts_code = str(row["ts_code"])
    snippet = stock_segment(str(row["raw_content"] or ""), stock_name, str(row["symbol"]), ts_code)
    if not snippet:
        snippet = str(row["evidence_snippet"])
    return AnalystMentionEvidenceItem(
        mention_id=str(row["mention_id"]),
        message_id=str(row["message_id"]),
        analyst_id=str(row["analyst_id"]),
        analyst_display_name=str(row["analyst_display_name"]),
        ts_code=ts_code,
        stock_name=stock_name,
        message_time=datetime.fromisoformat(str(row["message_time"])),
        evidence_snippet=snippet,
        stock_count_in_message=int(row["stock_count_in_message"] or 1),
        quality_flags=_quality_flags(row["quality_flags"]),
        window_days=window,
        status=str(row["status"]) if row["status"] else None,
        target_trade_date=str(row["target_trade_date"]) if row["target_trade_date"] else None,
        return_rate=float(row["return_rate"]) if row["return_rate"] is not None else None,
        positive=bool(row["positive"]) if row["positive"] is not None else None,
        excess_return_rate=(
            float(row["excess_return_rate"]) if row["excess_return_rate"] is not None else None
        ),
    )


def _group_message_rows(
    rows: list[sqlite3.Row],
    *,
    window: int,
) -> list[AnalystMentionMessageEvidenceItem]:
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(str(row["message_id"]), []).append(row)
    return [_message_item(items, window=window) for items in grouped.values()]


def _message_item(
    rows: list[sqlite3.Row],
    *,
    window: int,
) -> AnalystMentionMessageEvidenceItem:
    first = rows[0]
    items = [_item(row, window=window) for row in rows]
    quality_flags = tuple(sorted({flag for item in items for flag in item.quality_flags}))
    succeeded = [item for item in items if item.status == "succeeded" and item.return_rate is not None]
    excess_values = [
        float(item.excess_return_rate)
        for item in succeeded
        if item.excess_return_rate is not None
    ]
    positive_values = [1 if item.positive else 0 for item in succeeded if item.positive is not None]
    returns = [float(item.return_rate) for item in succeeded if item.return_rate is not None]
    metrics: dict[str, float | int] = {
        "stock_count": len(items),
        "succeeded_count": len(succeeded),
        "pending_count": sum(1 for item in items if item.status == "pending"),
        "missing_price_count": sum(1 for item in items if item.status == "missing_price"),
        "failed_count": sum(1 for item in items if item.status == "failed"),
    }
    if returns:
        best = max(succeeded, key=lambda item: float(item.return_rate or 0))
        worst = min(succeeded, key=lambda item: float(item.return_rate or 0))
        metrics["avg_return"] = round(sum(returns) / len(returns), 6)
        metrics["best_return"] = round(float(best.return_rate or 0), 6)
        metrics["worst_return"] = round(float(worst.return_rate or 0), 6)
    if excess_values:
        metrics["avg_excess"] = round(sum(excess_values) / len(excess_values), 6)
    if positive_values:
        metrics["positive_rate"] = round(sum(positive_values) / len(positive_values), 4)
    return AnalystMentionMessageEvidenceItem(
        message_id=str(first["message_id"]),
        analyst_id=str(first["analyst_id"]),
        analyst_display_name=str(first["analyst_display_name"]),
        message_time=datetime.fromisoformat(str(first["message_time"])),
        raw_content=str(first["raw_content"] or ""),
        stock_count=len(items),
        mentioned_stock_count=max(int(row["stock_count_in_message"] or 1) for row in rows),
        quality_flags=quality_flags,
        window_days=window,
        metrics=metrics,
        items=sorted(
            items,
            key=lambda item: (
                item.status == "succeeded",
                float(item.return_rate or -999),
            ),
            reverse=True,
        ),
    )



def _validate_inputs(start_time: datetime, end_time: datetime, window: int, limit: int) -> None:
    if end_time <= start_time:
        raise ValueError("end_time 必须晚于 start_time")
    if window < 1 or window > 30:
        raise ValueError("window 必须在 1 到 30 之间")
    if limit < 1 or limit > 200:
        raise ValueError("limit 必须在 1 到 200 之间")


def _quality_flags(value: object) -> tuple[str, ...]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return ()
    if not isinstance(parsed, list):
        return ()
    return tuple(str(item) for item in parsed)
