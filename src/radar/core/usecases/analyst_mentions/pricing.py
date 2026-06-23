from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

from radar.core.config import RadarConfig
from radar.core.storage import update_run_progress
from radar.core.tushare import history
from radar.core.tushare.client import call
from radar.core.tushare.exceptions import TushareConfigError
from radar.core.usecases.analyst_mentions.models import (
    AnalystMentionBacktestWindow,
    AnalystMentionEvent,
)

_PROGRESS_EVERY = 500
_DAILY_FULL_DAY_MIN_ROWS = 3000


def prewarm_daily_prices(
    config: RadarConfig,
    conn: sqlite3.Connection,
    *,
    open_dates: list[str],
    benchmark_ts_code: str,
    run_id: str,
) -> dict[str, int]:
    """按交易日批量预热日线，避免回测阶段逐股补行情。"""

    stats = {
        "prewarm_trade_day_count": 0,
        "prewarm_daily_row_count": 0,
        "prewarm_skipped_day_count": 0,
        "prewarm_index_row_count": 0,
    }
    daily_spec = history.spec_for("daily")
    if daily_spec is None or not open_dates:
        return stats
    for index, trade_date in enumerate(open_dates, start=1):
        if _daily_row_count(conn, trade_date) >= _DAILY_FULL_DAY_MIN_ROWS:
            stats["prewarm_skipped_day_count"] += 1
            continue
        rows = call(config, "daily", {"trade_date": trade_date})
        stats["prewarm_trade_day_count"] += 1
        stats["prewarm_daily_row_count"] += history.put_rows(
            config.market_database_path,
            daily_spec,
            rows,
        )
        if index % 5 == 0 or index == len(open_dates):
            update_run_progress(
                config.database_path,
                run_id,
                metadata={"stage": "批量补齐日线缓存", **stats},
            )
    stats["prewarm_index_row_count"] = len(
        call(
            config,
            "index_daily",
            {
                "ts_code": benchmark_ts_code,
                "start_date": open_dates[0],
                "end_date": open_dates[-1],
            },
        )
    )
    update_run_progress(
        config.database_path,
        run_id,
        metadata={"stage": "批量补齐日线缓存完成", **stats},
    )
    return stats


class PriceStore:
    def __init__(
        self,
        config: RadarConfig,
        conn: sqlite3.Connection,
        *,
        start_key: str,
        end_key: str,
        remote_enabled: bool = True,
    ) -> None:
        self.config = config
        self.conn = conn
        self.start_key = start_key
        self.end_key = end_key
        self.remote_enabled = remote_enabled
        self._cache: dict[tuple[str, str], dict[str, float]] = {}

    def closes(self, api_name: str, ts_code: str, start_key: str, end_key: str) -> dict[str, float]:
        key = (api_name, ts_code)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        values = self._local_closes(api_name, ts_code)
        if self.remote_enabled and not _has_price_range(values, start_key, end_key):
            values.update(self._remote_closes(api_name, ts_code, start_key, end_key))
        self._cache[key] = values
        return values

    def _local_closes(self, api_name: str, ts_code: str) -> dict[str, float]:
        rows = self.conn.execute(
            """
            SELECT date_key, data
            FROM tushare_history
            WHERE api_name = ? AND ts_code = ?
            """,
            (api_name, ts_code),
        ).fetchall()
        values: dict[str, float] = {}
        for row in rows:
            payload = _json_dict(row["data"])
            close = payload.get("close")
            if close is not None:
                values[str(row["date_key"])] = float(close)
        return values

    def _remote_closes(
        self,
        api_name: str,
        ts_code: str,
        start_key: str,
        end_key: str,
    ) -> dict[str, float]:
        try:
            rows = call(
                self.config,
                api_name,
                {
                    "ts_code": ts_code,
                    "start_date": min(start_key, self.start_key),
                    "end_date": max(end_key, self.end_key),
                },
            )
        except TushareConfigError:
            return {}
        values: dict[str, float] = {}
        for row in rows:
            trade_date = row.get("trade_date")
            close = row.get("close")
            if trade_date is not None and close is not None:
                values[str(trade_date)] = float(close)
        return values


def apply_effective_dedupe(
    mentions: list[AnalystMentionEvent],
    *,
    open_dates: list[str],
    cooldown_trade_days: int,
) -> list[AnalystMentionEvent]:
    open_index = {trade_date: index for index, trade_date in enumerate(open_dates)}
    last_effective: dict[str, int] = {}
    result: list[AnalystMentionEvent] = []
    for item in sorted(mentions, key=lambda value: (value.message_time, value.mention_id)):
        trade_date = base_trade_date(open_dates, item.event_date)
        trade_index = open_index.get(trade_date or "")
        previous = last_effective.get(item.dedupe_key)
        if (
            previous is not None
            and trade_index is not None
            and trade_index - previous <= cooldown_trade_days
        ):
            result.append(
                item.model_copy(
                    update={"is_effective": False, "dedupe_reason": "cooldown_repeat"}
                )
            )
            continue
        if trade_index is not None:
            last_effective[item.dedupe_key] = trade_index
        result.append(item)
    return result


def refresh_windows(
    conn: sqlite3.Connection,
    prices: PriceStore,
    mentions: list[AnalystMentionEvent],
    *,
    open_dates: list[str],
    windows: list[int],
    benchmark_ts_code: str,
    run_id: str,
    config: RadarConfig,
) -> dict[str, int]:
    stats = {
        "refreshed_count": 0,
        "pending_count": 0,
        "missing_price_count": 0,
        "failed_count": 0,
    }
    effective_mentions = [item for item in mentions if item.is_effective]
    for index, item in enumerate(effective_mentions, start=1):
        for window in windows:
            result = backtest_mention_window(
                prices,
                item,
                window,
                open_dates=open_dates,
                benchmark_ts_code=benchmark_ts_code,
            )
            upsert_window(conn, result)
            if result.status == "succeeded":
                stats["refreshed_count"] += 1
            elif result.status == "pending":
                stats["pending_count"] += 1
            elif result.status == "missing_price":
                stats["missing_price_count"] += 1
            else:
                stats["failed_count"] += 1
        if index % _PROGRESS_EVERY == 0 or index == len(effective_mentions):
            conn.commit()
            update_run_progress(
                config.database_path,
                run_id,
                raw_count=index,
                stored_count=stats["refreshed_count"],
                metadata={
                    "stage": "刷新分析师提及表现",
                    "effective_mention_count": len(effective_mentions),
                    **stats,
                },
            )
    conn.commit()
    return stats


def backtest_mention_window(
    prices: PriceStore,
    mention: AnalystMentionEvent,
    window: int,
    *,
    open_dates: list[str],
    benchmark_ts_code: str,
) -> AnalystMentionBacktestWindow:
    now = datetime.now()
    base, target = target_trade_dates(open_dates, mention.event_date, window)
    if base is None or target is None:
        return AnalystMentionBacktestWindow(
            mention_id=mention.mention_id,
            window_days=window,
            benchmark_ts_code=benchmark_ts_code,
            base_trade_date=base,
            target_trade_date=target,
            status="pending",
            updated_at=now,
        )
    lookup_start = _date_key(_parse_key(base) - timedelta(days=7))
    stock_prices = prices.closes("daily", mention.ts_code, lookup_start, target)
    base_date, base_close = latest_close_on_or_before(stock_prices, base)
    target_close = stock_prices.get(target)
    if base_date is None or base_close is None or target_close is None:
        return AnalystMentionBacktestWindow(
            mention_id=mention.mention_id,
            window_days=window,
            benchmark_ts_code=benchmark_ts_code,
            base_trade_date=base_date or base,
            target_trade_date=target,
            base_close=base_close,
            target_close=target_close,
            status="missing_price",
            error_message="missing_stock_price",
            updated_at=now,
        )
    benchmark_prices = prices.closes("index_daily", benchmark_ts_code, lookup_start, target)
    _, benchmark_base = latest_close_on_or_before(benchmark_prices, base)
    benchmark_target = benchmark_prices.get(target)
    stock_return = (target_close - base_close) / base_close
    benchmark_return = None
    excess_return = None
    if benchmark_base is not None and benchmark_target is not None:
        benchmark_return = (benchmark_target - benchmark_base) / benchmark_base
        excess_return = stock_return - benchmark_return
    return AnalystMentionBacktestWindow(
        mention_id=mention.mention_id,
        window_days=window,
        benchmark_ts_code=benchmark_ts_code,
        base_trade_date=base_date,
        target_trade_date=target,
        base_close=round(base_close, 6),
        target_close=round(target_close, 6),
        return_rate=round(stock_return, 6),
        positive=stock_return > 0,
        benchmark_base_close=round(benchmark_base, 6) if benchmark_base is not None else None,
        benchmark_target_close=round(benchmark_target, 6) if benchmark_target is not None else None,
        benchmark_return_rate=round(benchmark_return, 6) if benchmark_return is not None else None,
        excess_return_rate=round(excess_return, 6) if excess_return is not None else None,
        status="succeeded",
        updated_at=now,
    )


def upsert_window(conn: sqlite3.Connection, result: AnalystMentionBacktestWindow) -> None:
    conn.execute(
        """
        INSERT INTO analyst_stock_mention_windows (
            mention_id, window_days, benchmark_ts_code, base_trade_date, target_trade_date,
            base_close, target_close, return_rate, positive, benchmark_base_close,
            benchmark_target_close, benchmark_return_rate, excess_return_rate,
            status, error_message, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(mention_id, window_days, benchmark_ts_code) DO UPDATE SET
            base_trade_date = excluded.base_trade_date,
            target_trade_date = excluded.target_trade_date,
            base_close = excluded.base_close,
            target_close = excluded.target_close,
            return_rate = excluded.return_rate,
            positive = excluded.positive,
            benchmark_base_close = excluded.benchmark_base_close,
            benchmark_target_close = excluded.benchmark_target_close,
            benchmark_return_rate = excluded.benchmark_return_rate,
            excess_return_rate = excluded.excess_return_rate,
            status = excluded.status,
            error_message = excluded.error_message,
            updated_at = excluded.updated_at
        """,
        (
            result.mention_id,
            result.window_days,
            result.benchmark_ts_code,
            result.base_trade_date,
            result.target_trade_date,
            result.base_close,
            result.target_close,
            result.return_rate,
            int(result.positive) if result.positive is not None else None,
            result.benchmark_base_close,
            result.benchmark_target_close,
            result.benchmark_return_rate,
            result.excess_return_rate,
            result.status,
            result.error_message,
            result.updated_at.isoformat(),
        ),
    )


def open_trade_dates(
    config: RadarConfig,
    conn: sqlite3.Connection,
    *,
    start_date: date,
    as_of: date,
    remote_enabled: bool = True,
) -> list[str]:
    if remote_enabled:
        remote_dates = _remote_trade_dates(config, start_date=start_date, as_of=as_of)
        if remote_dates:
            return remote_dates
    rows = conn.execute(
        """
        SELECT DISTINCT date_key
        FROM tushare_history
        WHERE api_name = 'daily' AND date_key <= ?
        ORDER BY date_key ASC
        """,
        (as_of.strftime("%Y%m%d"),),
    ).fetchall()
    return [str(row["date_key"]) for row in rows]


def _remote_trade_dates(config: RadarConfig, *, start_date: date, as_of: date) -> list[str]:
    try:
        rows = call(
            config,
            "trade_cal",
            {
                "exchange": "",
                "start_date": _date_key(start_date - timedelta(days=10)),
                "end_date": _date_key(as_of),
            },
            fields="cal_date,is_open",
        )
    except TushareConfigError:
        return []
    dates = [
        str(row["cal_date"])
        for row in rows
        if str(row.get("is_open")) in {"1", "1.0", "True", "true"}
    ]
    return sorted(set(dates))


def _daily_row_count(conn: sqlite3.Connection, trade_date: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM tushare_history
        WHERE api_name = 'daily' AND date_key = ?
        """,
        (trade_date,),
    ).fetchone()
    return int(row[0] or 0)


def target_trade_dates(
    open_dates: list[str],
    event_date: str,
    window: int,
) -> tuple[str | None, str | None]:
    base_index = None
    for index, trade_date in enumerate(open_dates):
        if trade_date <= event_date:
            base_index = index
        else:
            break
    if base_index is None:
        return None, None
    target_index = base_index + window
    if target_index >= len(open_dates):
        return open_dates[base_index], None
    return open_dates[base_index], open_dates[target_index]


def base_trade_date(open_dates: list[str], event_date: str) -> str | None:
    value = None
    for trade_date in open_dates:
        if trade_date <= event_date:
            value = trade_date
        else:
            break
    return value


def latest_close_on_or_before(
    prices: dict[str, float],
    trade_date: str,
) -> tuple[str | None, float | None]:
    candidates = [key for key in prices if key <= trade_date]
    if not candidates:
        return None, None
    key = max(candidates)
    return key, prices[key]


def _has_price_range(prices: dict[str, float], start_key: str, end_key: str) -> bool:
    return bool(latest_close_on_or_before(prices, start_key)[1] and prices.get(end_key))


def _date_key(value: date) -> str:
    return value.strftime("%Y%m%d")


def _parse_key(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
