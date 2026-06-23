from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime
from statistics import median
from typing import Any

from radar.core.config import RadarConfig
from radar.core.models import MessageSource
from radar.core.storage import connect, init_db
from radar.core.usecases.analyst_mentions.models import (
    ANALYST_MENTION_EXTRACTOR_VERSION,
    DEFAULT_ANALYST_MENTION_WINDOWS,
    AnalystMentionSummaryResult,
    AnalystMentionSummaryRow,
)

_RANK_RETURN_NORMALIZER = 0.20
_RANK_SAMPLE_HALF_LIFE = 8
_RANK_WEIGHTS = {
    "avg_excess": 0.40,
    "avg_return": 0.25,
    "positive_rate_edge": 0.20,
    "median_return": 0.15,
}


def summarize_analyst_stock_mentions(
    config: RadarConfig,
    *,
    start_time: datetime,
    end_time: datetime,
    windows: list[int] | None = None,
    source: MessageSource | None = None,
    min_count: int = 3,
    limit: int = 20,
    include_broad_list: bool = False,
    extractor_version: str = ANALYST_MENTION_EXTRACTOR_VERSION,
) -> AnalystMentionSummaryResult:
    """汇总分析师近期股票提及后的已成熟表现。"""

    _validate_inputs(start_time, end_time, min_count, limit)
    window_values = sorted(set(windows or DEFAULT_ANALYST_MENTION_WINDOWS))
    conn = connect(config.database_path)
    try:
        init_db(conn)
        rows = _window_rows(
            conn,
            start_time=start_time,
            end_time=end_time,
            windows=window_values,
            source=source,
            include_broad_list=include_broad_list,
            extractor_version=extractor_version,
        )
        latest_event_times = _latest_event_times(
            conn,
            start_time=start_time,
            end_time=end_time,
            source=source,
            include_broad_list=include_broad_list,
            extractor_version=extractor_version,
        )
    finally:
        conn.close()
    grouped = _group_by_analyst(rows)
    primary_window = _primary_window(window_values)
    summary_rows = [
        _summary_row(
            items,
            windows=window_values,
            latest_event_time=latest_event_times.get(str(items[0]["analyst_id"])),
        )
        for items in grouped.values()
    ]
    summary_rows.sort(key=lambda row: _summary_sort_key(row, primary_window), reverse=True)
    return AnalystMentionSummaryResult(
        start_time=start_time,
        end_time=end_time,
        windows=window_values,
        row_count=len(summary_rows),
        rows=summary_rows[:limit],
    )


def _window_rows(
    conn: sqlite3.Connection,
    *,
    start_time: datetime,
    end_time: datetime,
    windows: list[int],
    source: MessageSource | None,
    include_broad_list: bool,
    extractor_version: str,
) -> list[sqlite3.Row]:
    placeholders = ", ".join("?" for _ in windows)
    source_clause = "AND m.source = ?" if source else ""
    quality_clause = (
        ""
        if include_broad_list
        else """AND m.quality_flags NOT LIKE '%"broad_list"%'"""
    )
    params: list[Any] = [
        start_time.isoformat(),
        end_time.isoformat(),
        extractor_version,
        *windows,
    ]
    if source:
        params.append(source)
    return conn.execute(
        f"""
        SELECT
            m.mention_id, m.analyst_id, m.analyst_display_name, m.ts_code, m.stock_name,
            m.message_time, w.window_days, w.status, w.return_rate, w.positive, w.excess_return_rate
        FROM analyst_stock_mentions m
        JOIN analyst_stock_mention_windows w ON w.mention_id = m.mention_id
        WHERE m.message_time >= ?
          AND m.message_time < ?
          AND m.extractor_version = ?
          AND m.is_effective = 1
          {quality_clause}
          AND w.window_days IN ({placeholders})
          {source_clause}
        ORDER BY m.message_time DESC, m.mention_id DESC
        """,
        params,
    ).fetchall()


def _latest_event_times(
    conn: sqlite3.Connection,
    *,
    start_time: datetime,
    end_time: datetime,
    source: MessageSource | None,
    include_broad_list: bool,
    extractor_version: str,
) -> dict[str, datetime]:
    source_clause = "AND source = ?" if source else ""
    quality_clause = (
        ""
        if include_broad_list
        else """AND quality_flags NOT LIKE '%"broad_list"%'"""
    )
    params: list[Any] = [
        start_time.isoformat(),
        end_time.isoformat(),
        extractor_version,
    ]
    if source:
        params.append(source)
    rows = conn.execute(
        f"""
        SELECT analyst_id, MAX(message_time) AS latest_event_time
        FROM analyst_stock_mentions
        WHERE message_time >= ?
          AND message_time < ?
          AND extractor_version = ?
          AND is_effective = 1
          {quality_clause}
          {source_clause}
        GROUP BY analyst_id
        """,
        params,
    ).fetchall()
    return {
        str(row["analyst_id"]): datetime.fromisoformat(str(row["latest_event_time"]))
        for row in rows
        if row["latest_event_time"]
    }


def _group_by_analyst(rows: list[sqlite3.Row]) -> dict[str, list[sqlite3.Row]]:
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        grouped[str(row["analyst_id"])].append(row)
    return grouped


def _summary_row(
    rows: list[sqlite3.Row],
    *,
    windows: list[int],
    latest_event_time: datetime | None,
) -> AnalystMentionSummaryRow:
    first = rows[0]
    metrics: dict[str, float | int] = {}
    for window in windows:
        window_rows = [row for row in rows if int(row["window_days"]) == window]
        succeeded_rows = [row for row in window_rows if str(row["status"]) == "succeeded"]
        pending_times = [
            datetime.fromisoformat(str(row["message_time"]))
            for row in window_rows
            if str(row["status"]) == "pending"
        ]
        positives = [int(row["positive"]) for row in succeeded_rows if row["positive"] is not None]
        returns = [
            float(row["return_rate"])
            for row in succeeded_rows
            if row["return_rate"] is not None
        ]
        excess = [
            float(row["excess_return_rate"])
            for row in succeeded_rows
            if row["excess_return_rate"] is not None
        ]
        if pending_times:
            latest_pending = max(pending_times)
            metrics[f"pending_count_t{window}"] = len(pending_times)
            metrics[f"pending_latest_date_t{window}"] = latest_pending.date().toordinal()
            metrics[f"pending_latest_timestamp_t{window}"] = round(latest_pending.timestamp(), 3)
        if positives:
            metrics[f"sample_count_t{window}"] = len(positives)
            metrics[f"positive_rate_t{window}"] = round(sum(positives) / len(positives), 4)
        if returns:
            metrics[f"avg_return_t{window}"] = round(sum(returns) / len(returns), 6)
            metrics[f"median_return_t{window}"] = round(float(median(returns)), 6)
        if excess:
            metrics[f"avg_excess_t{window}"] = round(sum(excess) / len(excess), 6)
        _add_ranking_metrics(metrics, window)
    return AnalystMentionSummaryRow(
        analyst_id=str(first["analyst_id"]),
        analyst_display_name=str(first["analyst_display_name"]),
        event_count=len({str(row["mention_id"]) for row in rows}),
        latest_event_time=latest_event_time or datetime.fromisoformat(str(first["message_time"])),
        metrics=metrics,
    )


def _summary_sort_key(
    row: AnalystMentionSummaryRow,
    window: int,
) -> tuple[float, float, float, float, float, int]:
    pending_latest_date = float(row.metrics.get(f"pending_latest_date_t{window}") or 0)
    pending_latest_time = float(row.metrics.get(f"pending_latest_timestamp_t{window}") or 0)
    avg_excess_value = row.metrics.get(f"avg_excess_t{window}")
    avg_excess = float(avg_excess_value) if avg_excess_value is not None else -999
    ranking_score = float(row.metrics.get(f"ranking_score_t{window}") or 0)
    avg_return = float(row.metrics.get(f"avg_return_t{window}") or 0)
    sample_count = int(row.metrics.get(f"sample_count_t{window}") or 0)
    return pending_latest_date, avg_excess, pending_latest_time, ranking_score, avg_return, sample_count


def _add_ranking_metrics(metrics: dict[str, float | int], window: int) -> None:
    sample_count = int(metrics.get(f"sample_count_t{window}") or 0)
    if sample_count <= 0:
        return
    avg_excess = float(metrics.get(f"avg_excess_t{window}") or 0)
    avg_return = float(metrics.get(f"avg_return_t{window}") or 0)
    positive_rate = float(metrics.get(f"positive_rate_t{window}") or 0)
    median_return = float(metrics.get(f"median_return_t{window}") or 0)
    sample_confidence = sample_count / (sample_count + _RANK_SAMPLE_HALF_LIFE)
    weighted_score = (
        _RANK_WEIGHTS["avg_excess"] * _normalize_return(avg_excess)
        + _RANK_WEIGHTS["avg_return"] * _normalize_return(avg_return)
        + _RANK_WEIGHTS["positive_rate_edge"] * ((positive_rate - 0.5) * 2)
        + _RANK_WEIGHTS["median_return"] * _normalize_return(median_return)
    )
    metrics[f"ranking_score_t{window}"] = round(weighted_score * sample_confidence * 100, 4)
    metrics[f"ranking_confidence_t{window}"] = round(sample_confidence, 4)


def _normalize_return(value: float) -> float:
    return max(-1.0, min(1.0, value / _RANK_RETURN_NORMALIZER))


def _primary_window(windows: list[int]) -> int:
    return 5 if 5 in windows else max(windows)


def _validate_inputs(start_time: datetime, end_time: datetime, min_count: int, limit: int) -> None:
    if end_time <= start_time:
        raise ValueError("end_time 必须晚于 start_time")
    if min_count < 1:
        raise ValueError("min_count 必须大于 0")
    if limit < 1:
        raise ValueError("limit 必须大于 0")
