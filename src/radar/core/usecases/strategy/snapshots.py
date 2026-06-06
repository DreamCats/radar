from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, Field

from radar.core.config import RadarConfig
from radar.core.db import migrate_market_db
from radar.core.store import connect, init_db
from radar.core.usecases.strategy.models import StrategyDashboard
from radar.core.usecases.strategy.signals import build_strategy_dashboard_from_conn

STRATEGY_TYPE = "opportunity_signal"
DEFAULT_SNAPSHOT_WINDOWS = (1, 3, 5, 10)
DEFAULT_SNAPSHOT_BENCHMARK = "000300.SH"


class StrategySnapshotSaveResult(BaseModel):
    snapshot_id: str
    strategy_type: str = STRATEGY_TYPE
    generated_at: datetime
    stock_count: int
    opportunity_count: int
    reused_existing: bool = False


class StrategySnapshotBackfillResult(BaseModel):
    snapshot_count: int = 0
    stock_count: int = 0
    refreshed_count: int = 0
    pending_count: int = 0
    missing_price_count: int = 0
    failed_count: int = 0
    windows: list[int]


class StrategyValidationMetric(BaseModel):
    label: str
    sample_count: int = 0
    win_rate: float | None = None
    average_return: float | None = None
    average_excess_return: float | None = None
    average_max_drawdown: float | None = None


class StrategyValidationSummary(BaseModel):
    window_days: int
    benchmark_ts_code: str
    snapshot_count: int = 0
    matured_stock_count: int = 0
    latest_snapshot_time: datetime | None = None
    by_decision_bucket: list[StrategyValidationMetric] = Field(default_factory=list)
    by_credibility_level: list[StrategyValidationMetric] = Field(default_factory=list)
    top_sources: list[StrategyValidationMetric] = Field(default_factory=list)


@dataclass(frozen=True)
class _PricePoint:
    date_key: str
    close: float


def save_strategy_snapshot(
    config: RadarConfig,
    *,
    days: int = 30,
    recent_days: int = 7,
    limit: int = 12,
) -> StrategySnapshotSaveResult:
    conn = connect(config.database_path)
    market_conn = connect(config.market_database_path)
    try:
        init_db(conn)
        migrate_market_db(market_conn)
        dashboard = build_strategy_dashboard_from_conn(
            conn,
            market_conn=market_conn,
            days=days,
            recent_days=recent_days,
            limit=limit,
        )
        return save_strategy_dashboard_snapshot(conn, dashboard)
    finally:
        conn.close()
        market_conn.close()


def save_strategy_dashboard_snapshot(
    conn: sqlite3.Connection,
    dashboard: StrategyDashboard,
    *,
    snapshot_id: str | None = None,
) -> StrategySnapshotSaveResult:
    snapshot_id = snapshot_id or uuid.uuid4().hex
    now = datetime.now()
    stocks = dashboard.stock_candidates
    conn.execute(
        """
        INSERT INTO strategy_snapshots (
            snapshot_id, strategy_type, start_time, end_time, recent_start_time,
            generated_at, created_at, opportunity_count, stock_count, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot_id,
            STRATEGY_TYPE,
            dashboard.start_time.isoformat(),
            dashboard.end_time.isoformat(),
            dashboard.recent_start_time.isoformat(),
            dashboard.generated_at.isoformat(),
            now.isoformat(),
            dashboard.opportunity_count,
            len(stocks),
            json.dumps(dashboard.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
        ),
    )
    for index, stock in enumerate(stocks, start=1):
        credibility = stock.event_credibility
        conn.execute(
            """
            INSERT INTO strategy_snapshot_stocks (
                snapshot_id, ts_code, stock_name, rank, decision_bucket, decision_reason,
                realtime_score, credibility_level, lifecycle_state, price_position,
                first_seen_time, latest_message_time, event_count, source_count,
                win_rate_t5, average_excess_return_t5, first_source_name, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                stock.ts_code,
                stock.stock_name,
                index,
                stock.decision_bucket,
                stock.decision_reason,
                stock.realtime_score,
                credibility.level if credibility else None,
                stock.lifecycle_state,
                stock.price_position,
                stock.first_seen_time.isoformat() if stock.first_seen_time else None,
                stock.latest_message_time.isoformat() if stock.latest_message_time else None,
                stock.event_count,
                stock.source_count,
                stock.win_rate_t5,
                stock.average_excess_return_t5,
                credibility.first_source_name if credibility else None,
                json.dumps(stock.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            ),
        )
    conn.commit()
    return StrategySnapshotSaveResult(
        snapshot_id=snapshot_id,
        generated_at=dashboard.generated_at,
        stock_count=len(stocks),
        opportunity_count=dashboard.opportunity_count,
    )


def backfill_strategy_snapshot_returns(
    config: RadarConfig,
    *,
    windows: list[int] | None = None,
    benchmark_ts_code: str = DEFAULT_SNAPSHOT_BENCHMARK,
    snapshot_id: str | None = None,
    snapshot_start_time: datetime | None = None,
    snapshot_end_time: datetime | None = None,
) -> StrategySnapshotBackfillResult:
    conn = connect(config.database_path)
    market_conn = connect(config.market_database_path)
    try:
        init_db(conn)
        migrate_market_db(market_conn)
        return backfill_strategy_snapshot_returns_from_conn(
            conn,
            market_conn,
            windows=windows or list(DEFAULT_SNAPSHOT_WINDOWS),
            benchmark_ts_code=benchmark_ts_code,
            snapshot_id=snapshot_id,
            snapshot_start_time=snapshot_start_time,
            snapshot_end_time=snapshot_end_time,
        )
    finally:
        conn.close()
        market_conn.close()


def backfill_strategy_snapshot_returns_from_conn(
    conn: sqlite3.Connection,
    market_conn: sqlite3.Connection,
    *,
    windows: list[int],
    benchmark_ts_code: str,
    snapshot_id: str | None = None,
    snapshot_start_time: datetime | None = None,
    snapshot_end_time: datetime | None = None,
) -> StrategySnapshotBackfillResult:
    snapshot_rows = _snapshot_rows(
        conn,
        snapshot_id=snapshot_id,
        snapshot_start_time=snapshot_start_time,
        snapshot_end_time=snapshot_end_time,
    )
    result = StrategySnapshotBackfillResult(snapshot_count=len(snapshot_rows), windows=sorted(set(windows)))
    for snapshot in snapshot_rows:
        stock_rows = _snapshot_stock_rows(conn, str(snapshot["snapshot_id"]))
        result.stock_count += len(stock_rows)
        base_date_key = datetime.fromisoformat(str(snapshot["end_time"])).strftime("%Y%m%d")
        for stock in stock_rows:
            for window in result.windows:
                status, payload = _window_return(
                    market_conn,
                    ts_code=str(stock["ts_code"]),
                    benchmark_ts_code=benchmark_ts_code,
                    base_date_key=base_date_key,
                    window=window,
                )
                _upsert_return(
                    conn,
                    snapshot_id=str(snapshot["snapshot_id"]),
                    ts_code=str(stock["ts_code"]),
                    window=window,
                    benchmark_ts_code=benchmark_ts_code,
                    status=status,
                    payload=payload,
                )
                if status == "succeeded":
                    result.refreshed_count += 1
                elif status == "pending":
                    result.pending_count += 1
                elif status == "missing_price":
                    result.missing_price_count += 1
                else:
                    result.failed_count += 1
    conn.commit()
    return result


def summarize_strategy_validation(
    config: RadarConfig,
    *,
    window_days: int = 5,
    benchmark_ts_code: str = DEFAULT_SNAPSHOT_BENCHMARK,
    source_limit: int = 8,
) -> StrategyValidationSummary:
    conn = connect(config.database_path)
    try:
        init_db(conn)
        return summarize_strategy_validation_from_conn(
            conn,
            window_days=window_days,
            benchmark_ts_code=benchmark_ts_code,
            source_limit=source_limit,
        )
    finally:
        conn.close()


def summarize_strategy_validation_from_conn(
    conn: sqlite3.Connection,
    *,
    window_days: int,
    benchmark_ts_code: str,
    source_limit: int = 8,
) -> StrategyValidationSummary:
    snapshot_stats = conn.execute(
        """
        SELECT COUNT(*) AS snapshot_count, MAX(generated_at) AS latest_snapshot_time
        FROM strategy_snapshots
        WHERE strategy_type = ?
        """,
        (STRATEGY_TYPE,),
    ).fetchone()
    matured_stock_count = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM strategy_snapshot_stocks s
        JOIN strategy_snapshot_returns r ON r.snapshot_id = s.snapshot_id AND r.ts_code = s.ts_code
        WHERE r.window_days = ?
          AND r.benchmark_ts_code = ?
          AND r.status = 'succeeded'
        """,
        (window_days, benchmark_ts_code),
    ).fetchone()
    latest_text = snapshot_stats["latest_snapshot_time"] if snapshot_stats else None
    return StrategyValidationSummary(
        window_days=window_days,
        benchmark_ts_code=benchmark_ts_code,
        snapshot_count=int(snapshot_stats["snapshot_count"] or 0) if snapshot_stats else 0,
        matured_stock_count=int(matured_stock_count["count"] or 0) if matured_stock_count else 0,
        latest_snapshot_time=datetime.fromisoformat(str(latest_text)) if latest_text else None,
        by_decision_bucket=_metric_rows(conn, "s.decision_bucket", window_days, benchmark_ts_code),
        by_credibility_level=_metric_rows(
            conn,
            "COALESCE(s.credibility_level, '待验证')",
            window_days,
            benchmark_ts_code,
        ),
        top_sources=_metric_rows(
            conn,
            "COALESCE(s.first_source_name, '未知来源')",
            window_days,
            benchmark_ts_code,
            limit=source_limit,
        ),
    )


def _metric_rows(
    conn: sqlite3.Connection,
    label_expr: str,
    window_days: int,
    benchmark_ts_code: str,
    *,
    limit: int | None = None,
) -> list[StrategyValidationMetric]:
    limit_sql = "LIMIT ?" if limit else ""
    params: list[object] = [window_days, benchmark_ts_code]
    if limit:
        params.append(limit)
    rows = conn.execute(
        f"""
        SELECT
            {label_expr} AS label,
            COUNT(*) AS sample_count,
            AVG(CASE WHEN r.excess_return_rate > 0 THEN 1.0 ELSE 0.0 END) AS win_rate,
            AVG(r.return_rate) AS average_return,
            AVG(r.excess_return_rate) AS average_excess_return,
            AVG(r.max_drawdown_rate) AS average_max_drawdown
        FROM strategy_snapshot_stocks s
        JOIN strategy_snapshot_returns r ON r.snapshot_id = s.snapshot_id AND r.ts_code = s.ts_code
        WHERE r.window_days = ?
          AND r.benchmark_ts_code = ?
          AND r.status = 'succeeded'
        GROUP BY label
        ORDER BY average_excess_return DESC, sample_count DESC
        {limit_sql}
        """,
        params,
    ).fetchall()
    return [
        StrategyValidationMetric(
            label=str(row["label"]),
            sample_count=int(row["sample_count"] or 0),
            win_rate=float(row["win_rate"]) if row["win_rate"] is not None else None,
            average_return=float(row["average_return"]) if row["average_return"] is not None else None,
            average_excess_return=float(row["average_excess_return"])
            if row["average_excess_return"] is not None
            else None,
            average_max_drawdown=float(row["average_max_drawdown"])
            if row["average_max_drawdown"] is not None
            else None,
        )
        for row in rows
    ]


def _snapshot_rows(
    conn: sqlite3.Connection,
    *,
    snapshot_id: str | None,
    snapshot_start_time: datetime | None = None,
    snapshot_end_time: datetime | None = None,
) -> list[sqlite3.Row]:
    if snapshot_id:
        return conn.execute(
            "SELECT snapshot_id, end_time FROM strategy_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchall()
    sql = ["SELECT snapshot_id, end_time FROM strategy_snapshots"]
    where: list[str] = []
    params: list[object] = []
    if snapshot_start_time is not None:
        where.append("end_time >= ?")
        params.append(snapshot_start_time.isoformat())
    if snapshot_end_time is not None:
        where.append("end_time <= ?")
        params.append(snapshot_end_time.isoformat())
    if where:
        sql.append("WHERE " + " AND ".join(where))
    sql.append("ORDER BY generated_at DESC")
    return conn.execute(" ".join(sql), params).fetchall()


def _snapshot_stock_rows(conn: sqlite3.Connection, snapshot_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT ts_code FROM strategy_snapshot_stocks WHERE snapshot_id = ? ORDER BY rank",
        (snapshot_id,),
    ).fetchall()


def _window_return(
    conn: sqlite3.Connection,
    *,
    ts_code: str,
    benchmark_ts_code: str,
    base_date_key: str,
    window: int,
) -> tuple[str, dict[str, object]]:
    stock_prices = _prices_from(conn, ts_code, start_key=base_date_key)
    benchmark_prices = _prices_from(conn, benchmark_ts_code, start_key=base_date_key, api_name="index_daily")
    if not stock_prices or not benchmark_prices:
        return "missing_price", {"error_message": "缺少基准日价格"}
    if len(stock_prices) <= window or len(benchmark_prices) <= window:
        return "pending", {
            "base_trade_date": stock_prices[0].date_key,
            "base_close": stock_prices[0].close,
            "error_message": "目标窗口尚未成熟",
        }
    base = stock_prices[0]
    target = stock_prices[window]
    benchmark_base = benchmark_prices[0]
    benchmark_target = benchmark_prices[window]
    return_rate = _ratio(target.close, base.close)
    benchmark_return = _ratio(benchmark_target.close, benchmark_base.close)
    return "succeeded", {
        "base_trade_date": base.date_key,
        "target_trade_date": target.date_key,
        "base_close": base.close,
        "target_close": target.close,
        "return_rate": return_rate,
        "benchmark_return_rate": benchmark_return,
        "excess_return_rate": return_rate - benchmark_return,
        "max_drawdown_rate": min(_ratio(item.close, base.close) for item in stock_prices[: window + 1]),
    }


def _prices_from(conn: sqlite3.Connection, ts_code: str, *, start_key: str, api_name: str = "daily") -> list[_PricePoint]:
    rows = conn.execute(
        """
        SELECT date_key, data
        FROM tushare_history
        WHERE api_name = ?
          AND ts_code = ?
          AND date_key >= ?
        ORDER BY date_key
        LIMIT 80
        """,
        (api_name, ts_code, start_key),
    ).fetchall()
    prices: list[_PricePoint] = []
    for row in rows:
        try:
            payload = json.loads(str(row["data"]))
            close = float(payload["close"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if close > 0:
            prices.append(_PricePoint(date_key=str(row["date_key"]), close=close))
    return prices


def _upsert_return(
    conn: sqlite3.Connection,
    *,
    snapshot_id: str,
    ts_code: str,
    window: int,
    benchmark_ts_code: str,
    status: str,
    payload: dict[str, object],
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO strategy_snapshot_returns (
            snapshot_id, ts_code, window_days, benchmark_ts_code,
            base_trade_date, target_trade_date, base_close, target_close,
            return_rate, benchmark_return_rate, excess_return_rate, max_drawdown_rate,
            status, error_message, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot_id,
            ts_code,
            window,
            benchmark_ts_code,
            payload.get("base_trade_date"),
            payload.get("target_trade_date"),
            payload.get("base_close"),
            payload.get("target_close"),
            payload.get("return_rate"),
            payload.get("benchmark_return_rate"),
            payload.get("excess_return_rate"),
            payload.get("max_drawdown_rate"),
            status,
            payload.get("error_message"),
            datetime.now().isoformat(),
        ),
    )


def _ratio(current: float, base: float) -> float:
    if base <= 0:
        return 0
    return current / base - 1
