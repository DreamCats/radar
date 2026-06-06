from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from radar.core.usecases.aggregation.storage import list_refine_results
from radar.core.usecases.strategy.models import (
    StrategyBacktestMetric,
    StrategyRelatedStock,
    StrategySourceSignal,
    StrategyStockCandidate,
    StrategyThemeBrief,
)


def related_stocks_for_anchors(
    conn: sqlite3.Connection,
    stats_list: list[Any],
    *,
    start_time: datetime,
    end_time: datetime,
    limit_per_anchor: int,
) -> dict[tuple[str, str], list[StrategyRelatedStock]]:
    if not stats_list:
        return {}

    values_sql = ", ".join("(?, ?)" for _ in stats_list)
    target_params: list[Any] = []
    for stats in stats_list:
        target_params.extend([stats.anchor_type, stats.name])
    rows = conn.execute(
        f"""
        WITH target(anchor_type, name) AS (
            VALUES {values_sql}
        ),
        matched AS (
            SELECT DISTINCT
                target.anchor_type,
                target.name,
                e.event_id,
                e.stock_name,
                e.ts_code,
                e.message_time,
                COALESCE(e.analyst_id, e.source_candidate) AS source_key,
                w.win,
                w.excess_return_rate
            FROM target
            JOIN message_anchors a
              ON a.anchor_type = target.anchor_type AND a.name = target.name
            JOIN recommendation_events e ON e.message_id = a.message_id
            JOIN recommendation_backtest_windows w ON w.event_id = e.event_id
            WHERE e.message_time >= ?
              AND e.message_time <= ?
              AND w.window_days = 5
              AND w.status = 'succeeded'
        ),
        grouped AS (
            SELECT
                anchor_type,
                name,
                stock_name,
                ts_code,
                COUNT(*) AS event_count,
                COUNT(DISTINCT source_key) AS source_count,
                AVG(win) AS win_rate,
                AVG(excess_return_rate) AS average_excess_return,
                MIN(message_time) AS first_time,
                MAX(message_time) AS latest_time
            FROM matched
            GROUP BY anchor_type, name, stock_name, ts_code
        ),
        ranked AS (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY anchor_type, name
                    ORDER BY average_excess_return DESC, event_count DESC, latest_time DESC
                ) AS rank
            FROM grouped
        )
        SELECT *
        FROM ranked
        WHERE rank <= ?
        ORDER BY anchor_type, name, rank
        """,
        [*target_params, start_time.isoformat(), end_time.isoformat(), limit_per_anchor],
    ).fetchall()
    by_anchor: dict[tuple[str, str], list[StrategyRelatedStock]] = {}
    for row in rows:
        key = (str(row["anchor_type"]), str(row["name"]))
        by_anchor.setdefault(key, []).append(_related_stock_from_row(row))
    return by_anchor


def backtest_metrics_for_anchors(
    conn: sqlite3.Connection,
    stats_list: list[Any],
    *,
    start_time: datetime,
    end_time: datetime,
) -> dict[tuple[str, str], StrategyBacktestMetric]:
    if not stats_list:
        return {}

    values_sql = ", ".join("(?, ?)" for _ in stats_list)
    target_params: list[Any] = []
    for stats in stats_list:
        target_params.extend([stats.anchor_type, stats.name])
    rows = conn.execute(
        f"""
        WITH target(anchor_type, name) AS (
            VALUES {values_sql}
        ),
        matched AS (
            SELECT DISTINCT
                target.anchor_type,
                target.name,
                e.event_id,
                w.status,
                w.win,
                w.excess_return_rate
            FROM target
            JOIN message_anchors a
              ON a.anchor_type = target.anchor_type AND a.name = target.name
            JOIN recommendation_events e ON e.message_id = a.message_id
            LEFT JOIN recommendation_backtest_windows w
              ON w.event_id = e.event_id AND w.window_days = 5
            WHERE e.message_time >= ?
              AND e.message_time <= ?
        )
        SELECT
            anchor_type,
            name,
            COUNT(DISTINCT event_id) AS event_count,
            COUNT(DISTINCT CASE WHEN status = 'succeeded' THEN event_id END) AS matured_event_count,
            COUNT(DISTINCT CASE WHEN status IS NULL OR status = 'pending' THEN event_id END) AS pending_event_count,
            AVG(CASE WHEN status = 'succeeded' THEN win END) AS win_rate,
            AVG(CASE WHEN status = 'succeeded' THEN excess_return_rate END) AS average_excess_return
        FROM matched
        GROUP BY anchor_type, name
        """,
        [*target_params, start_time.isoformat(), end_time.isoformat()],
    ).fetchall()
    return {
        (str(row["anchor_type"]), str(row["name"])): StrategyBacktestMetric(
            event_count=int(row["event_count"] or 0),
            matured_event_count=int(row["matured_event_count"] or 0),
            pending_event_count=int(row["pending_event_count"] or 0),
            win_rate_t5=float(row["win_rate"]) if row["win_rate"] is not None else None,
            average_excess_return_t5=float(row["average_excess_return"])
            if row["average_excess_return"] is not None
            else None,
        )
        for row in rows
    }


def top_sources_for_anchor(
    conn: sqlite3.Connection,
    *,
    name: str,
    anchor_type: str,
    recent_start_time: datetime,
    end_time: datetime,
    limit: int,
) -> list[StrategySourceSignal]:
    rows = conn.execute(
        """
        WITH matched AS (
            SELECT DISTINCT
                m.message_id,
                COALESCE(e.analyst_display_name, e.source_candidate, m.sender) AS source_name,
                e.event_id,
                m.message_time,
                w.win,
                w.excess_return_rate
            FROM message_anchors a
            JOIN messages m ON m.message_id = a.message_id
            LEFT JOIN recommendation_events e ON e.message_id = m.message_id
            LEFT JOIN recommendation_backtest_windows w
              ON w.event_id = e.event_id AND w.window_days = 5 AND w.status = 'succeeded'
            WHERE a.name = ?
              AND a.anchor_type = ?
              AND m.message_time >= ?
              AND m.message_time <= ?
        )
        SELECT
            source_name,
            COUNT(DISTINCT message_id) AS mention_count,
            COUNT(DISTINCT event_id) AS event_count,
            AVG(win) AS win_rate,
            AVG(excess_return_rate) AS average_excess_return,
            MAX(message_time) AS latest_time
        FROM matched
        GROUP BY source_name
        ORDER BY event_count DESC, mention_count DESC, average_excess_return DESC
        LIMIT ?
        """,
        (name, anchor_type, recent_start_time.isoformat(), end_time.isoformat(), limit),
    ).fetchall()
    return [_source_signal_from_row(row) for row in rows]


def source_quality(
    conn: sqlite3.Connection,
    *,
    start_time: datetime,
    end_time: datetime,
    limit: int,
) -> list[StrategySourceSignal]:
    rows = conn.execute(
        """
        SELECT
            COALESCE(e.analyst_display_name, e.source_candidate) AS source_name,
            COUNT(DISTINCT e.event_id) AS event_count,
            AVG(w.win) AS win_rate,
            AVG(w.excess_return_rate) AS average_excess_return,
            MAX(e.message_time) AS latest_time
        FROM recommendation_events e
        JOIN recommendation_backtest_windows w ON w.event_id = e.event_id
        WHERE e.message_time >= ?
          AND e.message_time <= ?
          AND w.window_days = 5
          AND w.status = 'succeeded'
        GROUP BY source_name
        HAVING event_count >= 3
        ORDER BY average_excess_return DESC, event_count DESC
        LIMIT ?
        """,
        (start_time.isoformat(), end_time.isoformat(), limit),
    ).fetchall()
    return [_source_signal_from_row(row, mention_count=0) for row in rows]


def stock_candidates(
    conn: sqlite3.Connection,
    *,
    start_time: datetime,
    end_time: datetime,
    limit: int,
) -> list[StrategyStockCandidate]:
    rows = conn.execute(
        """
        SELECT
            e.stock_name,
            e.ts_code,
            COUNT(DISTINCT e.event_id) AS event_count,
            COUNT(DISTINCT COALESCE(e.analyst_id, e.source_candidate)) AS source_count,
            GROUP_CONCAT(DISTINCT e.sector_name) AS sectors,
            AVG(w.win) AS win_rate,
            AVG(w.excess_return_rate) AS average_excess_return,
            MAX(e.message_time) AS latest_time
        FROM recommendation_events e
        JOIN recommendation_backtest_windows w ON w.event_id = e.event_id
        WHERE e.message_time >= ?
          AND e.message_time <= ?
          AND w.window_days = 5
          AND w.status = 'succeeded'
        GROUP BY e.stock_name, e.ts_code
        HAVING event_count >= 2
        ORDER BY average_excess_return DESC, source_count DESC, event_count DESC
        LIMIT ?
        """,
        (start_time.isoformat(), end_time.isoformat(), limit),
    ).fetchall()
    return [
        StrategyStockCandidate(
            stock_name=str(row["stock_name"]),
            ts_code=str(row["ts_code"]),
            event_count=int(row["event_count"] or 0),
            source_count=int(row["source_count"] or 0),
            sector_names=[item for item in str(row["sectors"] or "").split(",") if item],
            win_rate_t5=float(row["win_rate"]) if row["win_rate"] is not None else None,
            average_excess_return_t5=float(row["average_excess_return"])
            if row["average_excess_return"] is not None
            else None,
            latest_message_time=datetime.fromisoformat(str(row["latest_time"])) if row["latest_time"] else None,
        )
        for row in rows
    ]


def latest_theme_briefs(conn: sqlite3.Connection) -> list[StrategyThemeBrief]:
    try:
        results = list_refine_results(conn, limit=3)
    except ValueError:
        return []
    briefs: list[StrategyThemeBrief] = []
    for result in results:
        for theme in result.themes:
            briefs.append(
                StrategyThemeBrief(
                    theme_name=theme.theme_name,
                    confidence=theme.confidence,
                    actionability_score=theme.actionability_score,
                    catalysts=theme.catalysts[:3],
                    risk_notes=theme.risk_notes[:2],
                )
            )
    return briefs


def match_themes(name: str, themes: list[StrategyThemeBrief], *, limit: int) -> list[StrategyThemeBrief]:
    key = name.lower()
    matched = [
        theme
        for theme in themes
        if key in theme.theme_name.lower()
        or any(key in item.lower() for item in theme.catalysts)
        or any(key in item.lower() for item in theme.risk_notes)
    ]
    return matched[:limit]


def term_hits_for_anchor(
    conn: sqlite3.Connection,
    name: str,
    anchor_type: str,
    terms: tuple[str, ...],
    recent_start_time: datetime,
    end_time: datetime,
) -> list[str]:
    columns = ", ".join(f"SUM(CASE WHEN m.raw_content LIKE ? THEN 1 ELSE 0 END) AS t{i}" for i, _ in enumerate(terms))
    rows = conn.execute(
        f"""
        SELECT {columns}
        FROM message_anchors a
        JOIN messages m ON m.message_id = a.message_id
        WHERE a.name = ?
          AND a.anchor_type = ?
          AND m.message_time >= ?
          AND m.message_time <= ?
        """,
        [*(f"%{term}%" for term in terms), name, anchor_type, recent_start_time.isoformat(), end_time.isoformat()],
    ).fetchone()
    if rows is None:
        return []
    counts = [(term, int(rows[f"t{i}"] or 0)) for i, term in enumerate(terms)]
    return [term for term, count in sorted(counts, key=lambda item: item[1], reverse=True) if count > 0][:5]


def _related_stock_from_row(row: sqlite3.Row) -> StrategyRelatedStock:
    return StrategyRelatedStock(
        stock_name=str(row["stock_name"]),
        ts_code=str(row["ts_code"]),
        event_count=int(row["event_count"] or 0),
        source_count=int(row["source_count"] or 0),
        win_rate_t5=float(row["win_rate"]) if row["win_rate"] is not None else None,
        average_excess_return_t5=float(row["average_excess_return"]) if row["average_excess_return"] is not None else None,
        first_seen_time=datetime.fromisoformat(str(row["first_time"])) if row["first_time"] else None,
        latest_message_time=datetime.fromisoformat(str(row["latest_time"])) if row["latest_time"] else None,
    )


def _source_signal_from_row(row: sqlite3.Row, *, mention_count: int | None = None) -> StrategySourceSignal:
    return StrategySourceSignal(
        name=str(row["source_name"]),
        mention_count=int(row["mention_count"] if mention_count is None else mention_count or 0),
        event_count=int(row["event_count"] or 0),
        win_rate_t5=float(row["win_rate"]) if row["win_rate"] is not None else None,
        average_excess_return_t5=float(row["average_excess_return"]) if row["average_excess_return"] is not None else None,
        latest_message_time=datetime.fromisoformat(str(row["latest_time"])) if row["latest_time"] else None,
    )
