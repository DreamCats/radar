from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from radar.core.config import RadarConfig
from radar.core.db import migrate_market_db, migrate_message_db
from radar.core.store import connect
from radar.core.usecases.recommendation_backtest import DEFAULT_BENCHMARK_TS_CODE
from radar.core.usecases.strategy.models import (
    LeadSignalBucket,
    LeadSignalSample,
    LeadSignalSourceStat,
    LeadSignalSummary,
    LeadSignalWindow,
)

DEFAULT_LEAD_SIGNAL_WINDOWS = (1, 3, 5)


@dataclass
class _Window:
    window_days: int
    target_trade_date: str | None
    target_close: float | None
    return_rate: float | None
    excess_return_rate: float | None


@dataclass
class _Event:
    event_id: str
    event_date: str
    message_time: datetime
    source_name: str
    stock_name: str
    ts_code: str
    base_trade_date: str | None
    base_close: float | None
    message_day_pct_chg: float | None
    windows: dict[int, _Window] = field(default_factory=dict)


def summarize_lead_signals(
    config: RadarConfig,
    *,
    as_of_date: str | None = None,
    days: int = 30,
    limit: int = 20,
    source_limit: int = 12,
    benchmark_ts_code: str = DEFAULT_BENCHMARK_TS_CODE,
    message_day_max_pct: float = 2.0,
    strong_return_pct: float = 3.0,
    limit_like_pct: float = 9.5,
) -> LeadSignalSummary:
    if days < 1 or days > 180:
        raise ValueError("days 必须在 1 到 180 之间")
    if limit < 1 or limit > 100:
        raise ValueError("limit 必须在 1 到 100 之间")
    if source_limit < 1 or source_limit > 50:
        raise ValueError("source_limit 必须在 1 到 50 之间")
    if message_day_max_pct < -30 or message_day_max_pct > 30:
        raise ValueError("message_day_max_pct 必须在 -30 到 30 之间")
    if strong_return_pct < -30 or strong_return_pct > 30:
        raise ValueError("strong_return_pct 必须在 -30 到 30 之间")
    if limit_like_pct < 0 or limit_like_pct > 30:
        raise ValueError("limit_like_pct 必须在 0 到 30 之间")

    with connect(config.market_database_path) as market_conn:
        migrate_market_db(market_conn)
    with connect(config.database_path) as conn:
        migrate_message_db(conn)
        available_dates = _available_event_dates(conn)
        selected_date = _resolve_as_of_date(as_of_date, available_dates)
        now = datetime.now()
        if selected_date is None:
            return LeadSignalSummary(
                start_time=now,
                end_time=now,
                generated_at=now,
                as_of_date=as_of_date or now.strftime("%Y-%m-%d"),
                validation_days=days,
                benchmark_ts_code=benchmark_ts_code,
                message_day_max_pct=message_day_max_pct,
                strong_return_pct=strong_return_pct,
                limit_like_pct=limit_like_pct,
            )
        selected_start, selected_end = _date_bounds(selected_date)
        validation_start = selected_end - timedelta(days=days)
        conn.execute("ATTACH DATABASE ? AS market", (str(config.market_database_path),))
        try:
            day_events = _load_events(
                conn,
                start_time=selected_start,
                end_time=selected_end,
                benchmark_ts_code=benchmark_ts_code,
                succeeded_only=False,
            )
            validation_events = _load_events(
                conn,
                start_time=validation_start,
                end_time=selected_end,
                benchmark_ts_code=benchmark_ts_code,
                succeeded_only=True,
            )
        finally:
            conn.execute("DETACH DATABASE market")

    return _summarize(
        day_events=day_events,
        validation_events=[event for event in validation_events if 1 in event.windows],
        start_time=selected_start,
        end_time=selected_end,
        as_of_date=selected_date,
        available_dates=available_dates,
        validation_days=days,
        benchmark_ts_code=benchmark_ts_code,
        message_day_max_pct=message_day_max_pct,
        strong_return_pct=strong_return_pct,
        limit_like_pct=limit_like_pct,
        limit=limit,
        source_limit=source_limit,
    )


def _available_event_dates(conn: sqlite3.Connection, *, limit: int = 120) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT event_date
        FROM recommendation_events
        ORDER BY event_date DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [_display_date(str(row["event_date"])) for row in rows if row["event_date"]]


def _load_events(
    conn: sqlite3.Connection,
    *,
    start_time: datetime,
    end_time: datetime,
    benchmark_ts_code: str,
    succeeded_only: bool,
) -> list[_Event]:
    status_filter = "AND w.status = 'succeeded'" if succeeded_only else ""
    rows = conn.execute(
        f"""
        SELECT
            e.event_id,
            e.event_date,
            e.message_time,
            e.source_candidate,
            e.stock_name,
            e.ts_code,
            w.window_days,
            w.base_trade_date,
            w.base_close,
            w.target_trade_date,
            w.target_close,
            w.return_rate,
            w.excess_return_rate,
            CAST(json_extract(d.data, '$.close') AS REAL) AS daily_close,
            CAST(json_extract(d.data, '$.pct_chg') AS REAL) AS message_day_pct_chg
        FROM recommendation_events e
        LEFT JOIN recommendation_backtest_windows w
          ON w.event_id = e.event_id
         AND w.benchmark_ts_code = ?
         AND w.window_days IN (1, 3, 5)
        LEFT JOIN market.tushare_history d
          ON d.api_name = 'daily'
         AND d.ts_code = e.ts_code
         AND d.date_key = COALESCE(w.base_trade_date, e.event_date)
        WHERE e.action = 'bullish'
          AND e.message_time >= ?
          AND e.message_time < ?
          {status_filter}
        ORDER BY e.message_time ASC, e.event_id ASC, w.window_days ASC
        """,
        (benchmark_ts_code, start_time.isoformat(), end_time.isoformat()),
    ).fetchall()
    events: dict[str, _Event] = {}
    for row in rows:
        event_id = str(row["event_id"])
        event = events.get(event_id)
        if event is None:
            event = _Event(
                event_id=event_id,
                event_date=str(row["event_date"]),
                message_time=datetime.fromisoformat(str(row["message_time"])),
                source_name=str(row["source_candidate"] or "-"),
                stock_name=str(row["stock_name"]),
                ts_code=str(row["ts_code"]),
                base_trade_date=str(row["base_trade_date"]) if row["base_trade_date"] else None,
                base_close=_float_or_none(row["base_close"]) or _float_or_none(row["daily_close"]),
                message_day_pct_chg=_float_or_none(row["message_day_pct_chg"]),
            )
            events[event_id] = event
        if row["window_days"] is not None:
            event.windows[int(row["window_days"])] = _Window(
                window_days=int(row["window_days"]),
                target_trade_date=str(row["target_trade_date"]) if row["target_trade_date"] else None,
                target_close=_float_or_none(row["target_close"]),
                return_rate=_float_or_none(row["return_rate"]),
                excess_return_rate=_float_or_none(row["excess_return_rate"]),
            )
    return list(events.values())


def _summarize(
    *,
    day_events: list[_Event],
    validation_events: list[_Event],
    start_time: datetime,
    end_time: datetime,
    as_of_date: str,
    available_dates: list[str],
    validation_days: int,
    benchmark_ts_code: str,
    message_day_max_pct: float,
    strong_return_pct: float,
    limit_like_pct: float,
    limit: int,
    source_limit: int,
) -> LeadSignalSummary:
    events = validation_events
    day_non_hot = [event for event in day_events if _is_non_hot(event, message_day_max_pct)]
    day_limit_like = [event for event in day_events if _pct(event) is not None and (_pct(event) or 0) >= limit_like_pct]
    non_hot = [event for event in events if _is_non_hot(event, message_day_max_pct)]
    pre_rise = [event for event in non_hot if _t1_return(event) is not None and (_t1_return(event) or 0) > 0]
    strong = [
        event
        for event in non_hot
        if _t1_return(event) is not None and (_t1_return(event) or 0) >= strong_return_pct / 100
    ]
    limit_like = [event for event in events if _pct(event) is not None and (_pct(event) or 0) >= limit_like_pct]
    return LeadSignalSummary(
        start_time=start_time,
        end_time=end_time,
        generated_at=datetime.now(),
        as_of_date=as_of_date,
        available_dates=available_dates,
        validation_days=validation_days,
        benchmark_ts_code=benchmark_ts_code,
        message_day_max_pct=message_day_max_pct,
        strong_return_pct=strong_return_pct,
        limit_like_pct=limit_like_pct,
        day_event_count=len(day_events),
        day_stock_day_count=_stock_day_count(day_events),
        day_non_hot_event_count=len(day_non_hot),
        day_non_hot_stock_day_count=_stock_day_count(day_non_hot),
        day_limit_like_event_count=len(day_limit_like),
        day_limit_like_stock_day_count=_stock_day_count(day_limit_like),
        event_count=len(events),
        stock_day_count=_stock_day_count(events),
        non_hot_event_count=len(non_hot),
        non_hot_stock_day_count=_stock_day_count(non_hot),
        pre_rise_event_count=len(pre_rise),
        pre_rise_stock_day_count=_stock_day_count(pre_rise),
        strong_pre_rise_event_count=len(strong),
        strong_pre_rise_stock_day_count=_stock_day_count(strong),
        limit_like_event_count=len(limit_like),
        limit_like_stock_day_count=_stock_day_count(limit_like),
        buckets=_buckets(events, message_day_max_pct=message_day_max_pct, limit_like_pct=limit_like_pct),
        source_stats=_source_stats(
            events,
            message_day_max_pct=message_day_max_pct,
            strong_return_pct=strong_return_pct,
            limit_like_pct=limit_like_pct,
            limit=source_limit,
        ),
        samples=_samples(
            day_events,
            message_day_max_pct=message_day_max_pct,
            strong_return_pct=strong_return_pct,
            limit=limit,
        ),
    )


def _buckets(events: list[_Event], *, message_day_max_pct: float, limit_like_pct: float) -> list[LeadSignalBucket]:
    buckets: dict[tuple[str, int], list[_Window]] = defaultdict(list)
    for event in events:
        label = _bucket_label(event, message_day_max_pct=message_day_max_pct, limit_like_pct=limit_like_pct)
        for window in event.windows.values():
            buckets[(label, window.window_days)].append(window)
    order = {"未明显上涨": 0, "中间区间": 1, "涨停/近涨停": 2, "缺少T日涨幅": 3}
    out = [
        LeadSignalBucket(
            label=label,
            window_days=window_days,
            event_count=len(windows),
            average_return=_average([window.return_rate for window in windows]),
            average_excess_return=_average([window.excess_return_rate for window in windows]),
            up_rate=_rate([(window.return_rate or 0) > 0 for window in windows if window.return_rate is not None]),
        )
        for (label, window_days), windows in buckets.items()
    ]
    return sorted(out, key=lambda item: (order.get(item.label, 9), item.window_days))


def _source_stats(
    events: list[_Event],
    *,
    message_day_max_pct: float,
    strong_return_pct: float,
    limit_like_pct: float,
    limit: int,
) -> list[LeadSignalSourceStat]:
    by_source: dict[str, list[_Event]] = defaultdict(list)
    for event in events:
        by_source[event.source_name].append(event)
    rows: list[LeadSignalSourceStat] = []
    for source, items in by_source.items():
        non_hot = [event for event in items if _is_non_hot(event, message_day_max_pct)]
        pre_rise = [event for event in non_hot if _t1_return(event) is not None and (_t1_return(event) or 0) > 0]
        strong = [
            event
            for event in non_hot
            if _t1_return(event) is not None and (_t1_return(event) or 0) >= strong_return_pct / 100
        ]
        limit_like = [event for event in items if _pct(event) is not None and (_pct(event) or 0) >= limit_like_pct]
        rows.append(
            LeadSignalSourceStat(
                source_name=source,
                event_count=len(items),
                non_hot_event_count=len(non_hot),
                pre_rise_event_count=len(pre_rise),
                strong_pre_rise_event_count=len(strong),
                limit_like_event_count=len(limit_like),
                pre_rise_rate=len(pre_rise) / len(non_hot) if non_hot else None,
                average_t1_return=_average([_t1_return(event) for event in non_hot]),
                average_t1_excess_return=_average([_t1_excess(event) for event in non_hot]),
                latest_message_time=max((event.message_time for event in items), default=None),
            )
        )
    return sorted(
        rows,
        key=lambda item: (
            -item.strong_pre_rise_event_count,
            -(item.pre_rise_rate or 0),
            -item.non_hot_event_count,
            item.source_name,
        ),
    )[:limit]


def _samples(
    events: list[_Event],
    *,
    message_day_max_pct: float,
    strong_return_pct: float,
    limit: int,
) -> list[LeadSignalSample]:
    grouped: dict[tuple[str, str], list[_Event]] = defaultdict(list)
    for event in events:
        grouped[(event.event_date, event.ts_code)].append(event)
    samples: list[LeadSignalSample] = []
    for (_event_date, _ts_code), items in grouped.items():
        best = max(items, key=lambda item: _t1_return(item) or -1)
        sources = sorted({item.source_name for item in items if item.source_name})
        samples.append(
            LeadSignalSample(
                event_date=best.event_date,
                signal_label=_signal_label(
                    best,
                    message_day_max_pct=message_day_max_pct,
                    strong_return_pct=strong_return_pct,
                ),
                stock_name=best.stock_name,
                ts_code=best.ts_code,
                message_day_pct_chg=_pct(best),
                base_trade_date=best.base_trade_date,
                base_close=best.base_close,
                first_message_time=min(item.message_time for item in items),
                event_count=len(items),
                source_names=sources[:8],
                windows=[
                    LeadSignalWindow(
                        window_days=window.window_days,
                        target_trade_date=window.target_trade_date,
                        target_close=window.target_close,
                        return_rate=window.return_rate,
                        excess_return_rate=window.excess_return_rate,
                    )
                    for window in sorted(best.windows.values(), key=lambda item: item.window_days)
                ],
            )
        )
    return sorted(samples, key=_sample_sort_key, reverse=True)[:limit]


def _signal_label(event: _Event, *, message_day_max_pct: float, strong_return_pct: float) -> str:
    t1 = _t1_return(event)
    if not _is_non_hot(event, message_day_max_pct):
        return "追高观察"
    if t1 is None:
        return "涨前待验证"
    if t1 >= strong_return_pct / 100:
        return "强涨前命中"
    if t1 > 0:
        return "涨前命中"
    return "涨前未命中"


def _sample_sort_key(item: LeadSignalSample) -> tuple[int, float, int]:
    rank = {
        "强涨前命中": 5,
        "涨前命中": 4,
        "涨前待验证": 3,
        "追高观察": 2,
        "涨前未命中": 1,
    }.get(item.signal_label, 0)
    return rank, _window_return(item, 1) or 0, item.event_count


def _bucket_label(event: _Event, *, message_day_max_pct: float, limit_like_pct: float) -> str:
    pct = _pct(event)
    if pct is None:
        return "缺少T日涨幅"
    if pct < message_day_max_pct:
        return "未明显上涨"
    if pct >= limit_like_pct:
        return "涨停/近涨停"
    return "中间区间"


def _is_non_hot(event: _Event, message_day_max_pct: float) -> bool:
    pct = _pct(event)
    return pct is not None and pct < message_day_max_pct


def _pct(event: _Event) -> float | None:
    return event.message_day_pct_chg


def _t1_return(event: _Event) -> float | None:
    window = event.windows.get(1)
    return window.return_rate if window else None


def _t1_excess(event: _Event) -> float | None:
    window = event.windows.get(1)
    return window.excess_return_rate if window else None


def _stock_day_count(events: list[_Event]) -> int:
    return len({(event.event_date, event.ts_code) for event in events})


def _average(values: list[float | None]) -> float | None:
    valid = [value for value in values if value is not None]
    return sum(valid) / len(valid) if valid else None


def _rate(values: list[bool]) -> float | None:
    return sum(1 for value in values if value) / len(values) if values else None


def _window_return(sample: LeadSignalSample, window_days: int) -> float | None:
    window = next((item for item in sample.windows if item.window_days == window_days), None)
    return window.return_rate if window else None


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_as_of_date(value: str | None, available_dates: list[str]) -> str | None:
    if value:
        return _display_date(value)
    if available_dates:
        return available_dates[0]
    return None


def _date_bounds(value: str) -> tuple[datetime, datetime]:
    parsed = date.fromisoformat(_display_date(value))
    start = datetime.combine(parsed, time.min)
    return start, start + timedelta(days=1)


def _display_date(value: str) -> str:
    compact = value.strip()
    if len(compact) == 8 and compact.isdigit():
        return f"{compact[:4]}-{compact[4:6]}-{compact[6:]}"
    return date.fromisoformat(compact).isoformat()
