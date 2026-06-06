from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime

from radar.core.config import RadarConfig
from radar.core.models import MessageSource
from radar.core.store import connect, init_db
from radar.core.usecases.recommendation_backtest.models import (
    DEFAULT_BACKTEST_WINDOWS,
    BacktestGroupBy,
    RecommendationBacktestSummaryResult,
    RecommendationBacktestSummaryRow,
)


def summarize_recommendation_backtests(
    config: RadarConfig,
    *,
    start_time: datetime,
    end_time: datetime,
    group_by: BacktestGroupBy = "source",
    windows: list[int] | None = None,
    source: MessageSource | None = None,
    min_count: int = 1,
    limit: int = 20,
) -> RecommendationBacktestSummaryResult:
    """汇总 recommendation 回测结果；默认按来源候选输出画像。"""

    _validate_inputs(start_time, end_time, min_count, limit)
    window_values = sorted(set(windows or DEFAULT_BACKTEST_WINDOWS))
    conn = connect(config.database_path)
    try:
        init_db(conn)
        rows = _window_rows(conn, start_time=start_time, end_time=end_time, windows=window_values, source=source)
    finally:
        conn.close()

    grouped = _group_rows(rows, group_by=group_by)
    summary_rows = [
        _summary_row(key, items, group_by=group_by, windows=window_values)
        for key, items in grouped.items()
        if len({str(item["event_id"]) for item in items}) >= min_count
    ]
    summary_rows.sort(key=_summary_sort_key, reverse=True)
    limited_rows = summary_rows[:limit]
    return RecommendationBacktestSummaryResult(
        start_time=start_time,
        end_time=end_time,
        group_by=group_by,
        windows=window_values,
        row_count=len(summary_rows),
        rows=limited_rows,
    )


def _window_rows(
    conn: sqlite3.Connection,
    *,
    start_time: datetime,
    end_time: datetime,
    windows: list[int],
    source: MessageSource | None,
) -> list[sqlite3.Row]:
    placeholders = ", ".join("?" for _ in windows)
    source_clause = "AND e.source = ?" if source else ""
    params: list[object] = [start_time.isoformat(), end_time.isoformat(), *windows]
    if source:
        params.append(source)
    return conn.execute(
        f"""
        SELECT
            e.event_id, e.source_candidate, e.analyst_id, e.analyst_display_name,
            e.ts_code, e.stock_name, e.sector_anchor_type, e.sector_name, e.message_time,
            w.window_days, w.return_rate, w.win, w.excess_return_rate
        FROM recommendation_events e
        JOIN recommendation_backtest_windows w ON w.event_id = e.event_id
        WHERE e.message_time >= ?
          AND e.message_time < ?
          AND w.status = 'succeeded'
          AND w.window_days IN ({placeholders})
          {source_clause}
        ORDER BY e.message_time DESC
        """,
        params,
    ).fetchall()


def _group_rows(rows: list[sqlite3.Row], *, group_by: BacktestGroupBy) -> dict[str, list[sqlite3.Row]]:
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        key = _group_key(row, group_by)
        grouped[key].append(row)
    return grouped


def _group_key(row: sqlite3.Row, group_by: BacktestGroupBy) -> str:
    if group_by == "source_stock":
        return f"{row['source_candidate']}|{row['ts_code']}"
    if group_by == "analyst":
        return _analyst_key(row)
    if group_by == "analyst_stock":
        return f"{_analyst_key(row)}|{row['ts_code']}"
    if group_by == "sector":
        return _sector_key(row)
    if group_by == "analyst_sector":
        return f"{_analyst_key(row)}|{_sector_key(row)}"
    if group_by == "stock":
        return str(row["ts_code"])
    return str(row["source_candidate"])


def _summary_row(
    key: str,
    rows: list[sqlite3.Row],
    *,
    group_by: BacktestGroupBy,
    windows: list[int],
) -> RecommendationBacktestSummaryRow:
    event_ids = {str(row["event_id"]) for row in rows}
    first = rows[0]
    metrics: dict[str, float | int] = {"event_count": len(event_ids)}
    for window in windows:
        window_rows = [row for row in rows if int(row["window_days"]) == window]
        wins = [int(row["win"]) for row in window_rows if row["win"] is not None]
        returns = [float(row["return_rate"]) for row in window_rows if row["return_rate"] is not None]
        excess = [float(row["excess_return_rate"]) for row in window_rows if row["excess_return_rate"] is not None]
        if wins:
            metrics[f"sample_count_t{window}"] = len(wins)
            metrics[f"win_rate_t{window}"] = round(sum(wins) / len(wins), 4)
        if returns:
            metrics[f"avg_return_t{window}"] = round(sum(returns) / len(returns), 6)
        if excess:
            metrics[f"avg_excess_t{window}"] = round(sum(excess) / len(excess), 6)

    return RecommendationBacktestSummaryRow(
        key=key,
        source_candidate=str(first["source_candidate"]) if group_by in {"source", "source_stock"} else None,
        analyst_id=str(first["analyst_id"]) if group_by in {"analyst", "analyst_stock", "analyst_sector"} else None,
        analyst_display_name=(
            str(first["analyst_display_name"] or first["source_candidate"])
            if group_by in {"analyst", "analyst_stock", "analyst_sector"}
            else None
        ),
        ts_code=str(first["ts_code"]) if group_by in {"source_stock", "analyst_stock", "stock"} else None,
        stock_name=str(first["stock_name"]) if group_by in {"source_stock", "analyst_stock", "stock"} else None,
        sector_anchor_type=(
            str(first["sector_anchor_type"]) if group_by in {"sector", "analyst_sector"} and first["sector_anchor_type"] else None
        ),
        sector_name=str(first["sector_name"]) if group_by in {"sector", "analyst_sector"} and first["sector_name"] else None,
        event_count=len(event_ids),
        metrics=metrics,
    )


def _summary_sort_key(row: RecommendationBacktestSummaryRow) -> tuple[float, int, float, int]:
    win_rate = float(row.metrics.get("win_rate_t5") or 0)
    sample_count = int(row.metrics.get("sample_count_t5") or 0)
    avg_excess = float(row.metrics.get("avg_excess_t5") or 0)
    return win_rate, sample_count, avg_excess, row.event_count


def _validate_inputs(start_time: datetime, end_time: datetime, min_count: int, limit: int) -> None:
    if end_time <= start_time:
        raise ValueError("end_time 必须晚于 start_time")
    if min_count < 1:
        raise ValueError("min_count 必须大于 0")
    if limit < 1:
        raise ValueError("limit 必须大于 0")


def _analyst_key(row: sqlite3.Row) -> str:
    return str(row["analyst_id"] or row["source_candidate"])


def _sector_key(row: sqlite3.Row) -> str:
    if row["sector_name"]:
        return f"{row['sector_anchor_type'] or 'sector'}|{row['sector_name']}"
    return "未归因"
