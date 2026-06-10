from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timedelta

from radar.core.config import RadarConfig
from radar.core.models import MessageSource
from radar.core.runs import fail_run, finish_run, start_run, update_run_progress
from radar.core.store import connect, init_db
from radar.core.tushare.client import call
from radar.core.usecases.recommendation_backtest.events import (
    RECOMMENDATION_EVENT_EXTRACTOR_VERSION,
    list_recommendation_events,
    refresh_recommendation_events,
)
from radar.core.usecases.recommendation_backtest.models import (
    DEFAULT_BENCHMARK_TS_CODE,
    DEFAULT_BACKTEST_WINDOWS,
    BacktestWindowResult,
    RecommendationBacktestRefreshResult,
    RecommendationEvent,
)

BACKTEST_RUN_KIND = "recommendation_backtest_refresh"
_PROGRESS_EVERY = 25


class _PriceCache:
    def __init__(self, config: RadarConfig, *, start_key: str, end_key: str) -> None:
        self.config = config
        self.start_key = start_key
        self.end_key = end_key
        self._cache: dict[tuple[str, str], dict[str, float]] = {}

    def closes(self, api_name: str, ts_code: str, start_key: str, end_key: str) -> dict[str, float]:
        key = (api_name, ts_code)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        rows = call(
            self.config,
            api_name,
            {
                "ts_code": ts_code,
                "start_date": min(start_key, self.start_key),
                "end_date": max(end_key, self.end_key),
            },
        )
        values: dict[str, float] = {}
        for row in rows:
            trade_date = row.get("trade_date")
            close = row.get("close")
            if trade_date is None or close is None:
                continue
            values[str(trade_date)] = float(close)
        self._cache[key] = values
        return values


def refresh_recommendation_backtests(
    config: RadarConfig,
    *,
    as_of: date,
    window_days: int = 30,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    windows: list[int] | None = None,
    source: MessageSource | None = None,
    min_classification_confidence: float = 0.7,
    extractor_version: str = RECOMMENDATION_EVENT_EXTRACTOR_VERSION,
    benchmark_ts_code: str = DEFAULT_BENCHMARK_TS_CODE,
    force: bool = False,
    run_id: str | None = None,
) -> RecommendationBacktestRefreshResult:
    """刷新最近窗口内生命周期证据事件，并补齐已经成熟的 T+N 回测。"""

    window_values = _normalize_windows(windows)
    _validate_inputs(
        as_of,
        window_days,
        min_classification_confidence,
        benchmark_ts_code,
        start_time=start_time,
        end_time=end_time,
    )
    if start_time is None or end_time is None:
        start_time = datetime.combine(as_of - timedelta(days=window_days - 1), time.min)
        end_time = datetime.combine(as_of + timedelta(days=1), time.min)
    run_metadata = {
        "as_of": as_of.isoformat(),
        "window_days": window_days,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "windows": window_values,
        "source": source,
        "min_classification_confidence": min_classification_confidence,
        "extractor_version": extractor_version,
        "benchmark_ts_code": benchmark_ts_code,
        "force": force,
    }
    if run_id is None:
        run_id = start_run(
            config.database_path,
            kind=BACKTEST_RUN_KIND,
            target=f"{start_time.isoformat()}..{end_time.isoformat()}|as_of={as_of.isoformat()}",
            metadata=run_metadata,
        )

    conn = connect(config.database_path)
    try:
        init_db(conn)
        events, inserted_event_count = refresh_recommendation_events(
            config,
            conn,
            start_time=start_time,
            end_time=end_time,
            source=source,
            min_classification_confidence=min_classification_confidence,
            extractor_version=extractor_version,
        )
        conn.commit()
        if not events:
            events = list_recommendation_events(
                conn,
                start_time=start_time,
                end_time=end_time,
                source=source,
                extractor_version=extractor_version,
            )

        stats = _refresh_windows(
            conn,
            config,
            events,
            as_of=as_of,
            windows=window_values,
            benchmark_ts_code=benchmark_ts_code,
            force=force,
            run_id=run_id,
        )
        result = RecommendationBacktestRefreshResult(
            run_id=run_id,
            as_of=as_of,
            start_time=start_time,
            end_time=end_time,
            windows=window_values,
            benchmark_ts_code=benchmark_ts_code,
            event_count=len(events),
            inserted_event_count=inserted_event_count,
            **stats,
        )
        finish_run(
            config.database_path,
            run_id,
            status="skipped" if len(events) == 0 else "succeeded",
            raw_count=len(events),
            stored_count=result.refreshed_count,
            metadata=run_metadata | result.model_dump(mode="json"),
        )
        return result
    except BaseException as exc:
        fail_run(config.database_path, run_id, _run_error(exc))
        raise
    finally:
        conn.close()


def _refresh_windows(
    conn: sqlite3.Connection,
    config: RadarConfig,
    events: list[RecommendationEvent],
    *,
    as_of: date,
    windows: list[int],
    benchmark_ts_code: str,
    force: bool,
    run_id: str,
) -> dict[str, int]:
    min_event_date = min(event.message_time.date() for event in events) if events else as_of
    open_dates = _open_trade_dates(config, min_event_date, as_of)
    existing = _existing_statuses(conn, [event.event_id for event in events], benchmark_ts_code)
    prices = _PriceCache(
        config,
        start_key=_date_key(min_event_date - timedelta(days=17)),
        end_key=_date_key(as_of),
    )
    stats = {
        "refreshed_count": 0,
        "skipped_complete_count": 0,
        "pending_count": 0,
        "missing_price_count": 0,
        "failed_count": 0,
    }

    for index, event in enumerate(events, start=1):
        for window in windows:
            if not force and existing.get((event.event_id, window)) == "succeeded":
                stats["skipped_complete_count"] += 1
                continue
            result = _backtest_event_window(
                prices,
                event,
                window,
                open_dates=open_dates,
                benchmark_ts_code=benchmark_ts_code,
            )
            _upsert_window(conn, result)
            if result.status == "succeeded":
                stats["refreshed_count"] += 1
            elif result.status == "pending":
                stats["pending_count"] += 1
            elif result.status == "missing_price":
                stats["missing_price_count"] += 1
            else:
                stats["failed_count"] += 1

        conn.commit()
        if index % _PROGRESS_EVERY == 0 or index == len(events):
            update_run_progress(
                config.database_path,
                run_id,
                raw_count=index,
                stored_count=stats["refreshed_count"],
                metadata={"stage": "刷新证据回测补齐", "event_count": len(events), "completed_event_count": index, **stats},
            )
    return stats


def _backtest_event_window(
    prices: _PriceCache,
    event: RecommendationEvent,
    window: int,
    *,
    open_dates: list[str],
    benchmark_ts_code: str,
) -> BacktestWindowResult:
    now = datetime.now()
    base_trade_date, target_trade_date = _target_trade_dates(open_dates, event.event_date, window)
    if base_trade_date is None or target_trade_date is None:
        return BacktestWindowResult(
            event_id=event.event_id,
            window_days=window,
            benchmark_ts_code=benchmark_ts_code,
            base_trade_date=base_trade_date,
            target_trade_date=target_trade_date,
            status="pending",
            updated_at=now,
        )

    lookup_start = _date_key(_parse_key(base_trade_date) - timedelta(days=7))
    stock_prices = prices.closes("daily", event.ts_code, lookup_start, target_trade_date)
    base_date, base_close = _latest_close_on_or_before(stock_prices, base_trade_date)
    target_close = stock_prices.get(target_trade_date)
    if base_date is None or base_close is None or target_close is None:
        return BacktestWindowResult(
            event_id=event.event_id,
            window_days=window,
            benchmark_ts_code=benchmark_ts_code,
            base_trade_date=base_date or base_trade_date,
            target_trade_date=target_trade_date,
            base_close=base_close,
            target_close=target_close,
            status="missing_price",
            error_message="missing_stock_price",
            updated_at=now,
        )

    benchmark_prices = prices.closes("index_daily", benchmark_ts_code, lookup_start, target_trade_date)
    benchmark_base_date, benchmark_base = _latest_close_on_or_before(benchmark_prices, base_trade_date)
    benchmark_target = benchmark_prices.get(target_trade_date)
    stock_return = (target_close - base_close) / base_close
    benchmark_return = None
    excess_return = None
    if benchmark_base_date is not None and benchmark_base is not None and benchmark_target is not None:
        benchmark_return = (benchmark_target - benchmark_base) / benchmark_base
        excess_return = stock_return - benchmark_return

    return BacktestWindowResult(
        event_id=event.event_id,
        window_days=window,
        benchmark_ts_code=benchmark_ts_code,
        base_trade_date=base_date,
        target_trade_date=target_trade_date,
        base_close=round(base_close, 6),
        target_close=round(target_close, 6),
        return_rate=round(stock_return, 6),
        win=stock_return > 0 if event.action == "bullish" else stock_return < 0,
        benchmark_base_close=round(benchmark_base, 6) if benchmark_base is not None else None,
        benchmark_target_close=round(benchmark_target, 6) if benchmark_target is not None else None,
        benchmark_return_rate=round(benchmark_return, 6) if benchmark_return is not None else None,
        excess_return_rate=round(excess_return, 6) if excess_return is not None else None,
        status="succeeded",
        updated_at=now,
    )


def _open_trade_dates(config: RadarConfig, start_date: date, as_of: date) -> list[str]:
    cal_start = _date_key(start_date - timedelta(days=10))
    cal_end = _date_key(as_of)
    rows = call(
        config,
        "trade_cal",
        {"exchange": "", "start_date": cal_start, "end_date": cal_end},
        fields="cal_date,is_open",
    )
    dates = [str(row["cal_date"]) for row in rows if str(row.get("is_open")) in {"1", "1.0", "True", "true"}]
    return sorted(set(dates))


def _target_trade_dates(open_dates: list[str], event_date: str, window: int) -> tuple[str | None, str | None]:
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


def _existing_statuses(
    conn: sqlite3.Connection,
    event_ids: list[str],
    benchmark_ts_code: str,
) -> dict[tuple[str, int], str]:
    if not event_ids:
        return {}
    placeholders = ", ".join("?" for _ in event_ids)
    rows = conn.execute(
        f"""
        SELECT event_id, window_days, status
        FROM recommendation_backtest_windows
        WHERE benchmark_ts_code = ? AND event_id IN ({placeholders})
        """,
        [benchmark_ts_code, *event_ids],
    ).fetchall()
    return {(str(row["event_id"]), int(row["window_days"])): str(row["status"]) for row in rows}


def _upsert_window(conn: sqlite3.Connection, result: BacktestWindowResult) -> None:
    conn.execute(
        """
        INSERT INTO recommendation_backtest_windows (
            event_id, window_days, benchmark_ts_code, base_trade_date, target_trade_date,
            base_close, target_close, return_rate, win, benchmark_base_close,
            benchmark_target_close, benchmark_return_rate, excess_return_rate,
            status, error_message, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id, window_days, benchmark_ts_code) DO UPDATE SET
            base_trade_date = excluded.base_trade_date,
            target_trade_date = excluded.target_trade_date,
            base_close = excluded.base_close,
            target_close = excluded.target_close,
            return_rate = excluded.return_rate,
            win = excluded.win,
            benchmark_base_close = excluded.benchmark_base_close,
            benchmark_target_close = excluded.benchmark_target_close,
            benchmark_return_rate = excluded.benchmark_return_rate,
            excess_return_rate = excluded.excess_return_rate,
            status = excluded.status,
            error_message = excluded.error_message,
            updated_at = excluded.updated_at
        """,
        (
            result.event_id,
            result.window_days,
            result.benchmark_ts_code,
            result.base_trade_date,
            result.target_trade_date,
            result.base_close,
            result.target_close,
            result.return_rate,
            int(result.win) if result.win is not None else None,
            result.benchmark_base_close,
            result.benchmark_target_close,
            result.benchmark_return_rate,
            result.excess_return_rate,
            result.status,
            result.error_message,
            result.updated_at.isoformat(),
        ),
    )


def _latest_close_on_or_before(prices: dict[str, float], trade_date: str) -> tuple[str | None, float | None]:
    candidates = [key for key in prices if key <= trade_date]
    if not candidates:
        return None, None
    key = max(candidates)
    return key, prices[key]


def _normalize_windows(windows: list[int] | None) -> list[int]:
    values = list(windows or DEFAULT_BACKTEST_WINDOWS)
    if not values:
        raise ValueError("windows 不能为空")
    if any(value < 1 or value > 30 for value in values):
        raise ValueError("window 必须在 1 到 30 之间")
    return sorted(set(values))


def _validate_inputs(
    _as_of: date,
    window_days: int,
    min_classification_confidence: float,
    benchmark_ts_code: str,
    *,
    start_time: datetime | None,
    end_time: datetime | None,
) -> None:
    if window_days < 1:
        raise ValueError("window_days 必须大于 0")
    if min_classification_confidence < 0 or min_classification_confidence > 1:
        raise ValueError("min_classification_confidence 必须在 0 到 1 之间")
    if not benchmark_ts_code:
        raise ValueError("benchmark_ts_code 不能为空")
    if (start_time is None) != (end_time is None):
        raise ValueError("start_time 和 end_time 必须同时提供")
    if start_time is not None and end_time is not None and end_time <= start_time:
        raise ValueError("end_time 必须晚于 start_time")


def _run_error(exc: BaseException) -> BaseException:
    if isinstance(exc, KeyboardInterrupt):
        return RuntimeError("任务被中断")
    return exc


def _date_key(value: date) -> str:
    return value.strftime("%Y%m%d")


def _parse_key(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()
