from __future__ import annotations

from datetime import date, datetime, time, timedelta

from radar.core.config import RadarConfig
from radar.core.models import MessageSource
from radar.core.storage import connect, fail_run, finish_run, init_db, start_run
from radar.core.storage.db import migrate_market_db
from radar.core.usecases.analyst_mentions.extract import extract_mentions
from radar.core.usecases.analyst_mentions.models import (
    ANALYST_MENTION_EXTRACTOR_VERSION,
    DEFAULT_ANALYST_MENTION_WINDOWS,
    DEFAULT_BENCHMARK_TS_CODE,
    DEFAULT_COOLDOWN_TRADE_DAYS,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_REMOTE_PRICE_FETCH,
    QUALITY_FLAG_BROAD_LIST,
    AnalystMentionRefreshResult,
)
from radar.core.usecases.analyst_mentions.pricing import (
    PriceStore,
    apply_effective_dedupe,
    open_trade_dates,
    prewarm_daily_prices,
    refresh_windows,
)
from radar.core.usecases.analyst_mentions.storage import replace_mentions, upsert_analysts
from radar.core.tushare.stock_matcher import StockMatcher, load_stocks

ANALYST_MENTION_RUN_KIND = "analyst_stock_mention_backtest_refresh"


def refresh_analyst_stock_mentions(
    config: RadarConfig,
    *,
    as_of: date,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    windows: list[int] | None = None,
    source: MessageSource | None = None,
    cooldown_trade_days: int = DEFAULT_COOLDOWN_TRADE_DAYS,
    remote_price_fetch: bool = DEFAULT_REMOTE_PRICE_FETCH,
    extractor_version: str = ANALYST_MENTION_EXTRACTOR_VERSION,
    benchmark_ts_code: str = DEFAULT_BENCHMARK_TS_CODE,
    run_id: str | None = None,
) -> AnalystMentionRefreshResult:
    """从历史消息直接抽“人-股票提及”，并补齐本地 T+N 表现。"""

    window_values = _normalize_windows(windows)
    _validate_inputs(
        lookback_days,
        cooldown_trade_days,
        benchmark_ts_code,
        start_time,
        end_time,
    )
    if start_time is None or end_time is None:
        end_time = datetime.combine(as_of + timedelta(days=1), time.min)
        start_time = end_time - timedelta(days=lookback_days)
    metadata = _metadata(
        as_of=as_of,
        lookback_days=lookback_days,
        start_time=start_time,
        end_time=end_time,
        windows=window_values,
        source=source,
        cooldown_trade_days=cooldown_trade_days,
        remote_price_fetch=remote_price_fetch,
        extractor_version=extractor_version,
        benchmark_ts_code=benchmark_ts_code,
    )
    if run_id is None:
        target = (
            f"{source or 'all'}:{start_time.isoformat()}..{end_time.isoformat()}"
            f":v={extractor_version}"
        )
        run_id = start_run(
            config.database_path,
            kind=ANALYST_MENTION_RUN_KIND,
            target=target,
            metadata=metadata,
        )

    conn = connect(config.database_path)
    market_conn = connect(config.market_database_path)
    try:
        init_db(conn)
        migrate_market_db(market_conn)
        matcher = StockMatcher(load_stocks(market_conn))
        dates = open_trade_dates(
            config,
            market_conn,
            start_date=start_time.date(),
            as_of=as_of,
            remote_enabled=remote_price_fetch,
        )
        prewarm_stats = (
            prewarm_daily_prices(
                config,
                market_conn,
                open_dates=dates,
                benchmark_ts_code=benchmark_ts_code,
                run_id=run_id,
            )
            if remote_price_fetch
            else {}
        )
        (
            raw_mentions,
            scanned_count,
            stock_hit_count,
            source_broker_filtered_count,
        ) = extract_mentions(
            conn,
            matcher,
            start_time=start_time,
            end_time=end_time,
            source=source,
            extractor_version=extractor_version,
        )
        mentions = apply_effective_dedupe(
            raw_mentions,
            open_dates=dates,
            cooldown_trade_days=cooldown_trade_days,
        )
        replace_mentions(
            conn,
            mentions,
            start_time=start_time,
            end_time=end_time,
            source=source,
            extractor_version=extractor_version,
        )
        upsert_analysts(conn, mentions)
        stats = refresh_windows(
            conn,
            PriceStore(
                config,
                market_conn,
                start_key=_date_key(start_time.date() - timedelta(days=17)),
                end_key=_date_key(as_of),
                remote_enabled=remote_price_fetch,
            ),
            mentions,
            open_dates=dates,
            windows=window_values,
            benchmark_ts_code=benchmark_ts_code,
            run_id=run_id,
            config=config,
        )
        stats = prewarm_stats | stats
        result = _result(
            run_id=run_id,
            as_of=as_of,
            start_time=start_time,
            end_time=end_time,
            windows=window_values,
            benchmark_ts_code=benchmark_ts_code,
            extractor_version=extractor_version,
            scanned_count=scanned_count,
            stock_hit_count=stock_hit_count,
            raw_count=len(raw_mentions),
            source_broker_filtered_count=source_broker_filtered_count,
            broad_list_count=sum(
                1 for item in raw_mentions if QUALITY_FLAG_BROAD_LIST in item.quality_flags
            ),
            inserted_count=len(mentions),
            effective_count=sum(1 for item in mentions if item.is_effective),
            repeated_count=sum(1 for item in mentions if not item.is_effective),
            stats=stats,
        )
        finish_run(
            config.database_path,
            run_id,
            status="skipped" if not mentions else "succeeded",
            raw_count=scanned_count,
            stored_count=result.effective_mention_count,
            filtered_count=result.repeated_mention_count,
            metadata=metadata | result.model_dump(mode="json"),
        )
        return result
    except BaseException as exc:
        fail_run(config.database_path, run_id, _run_error(exc))
        raise
    finally:
        conn.close()
        market_conn.close()


def _normalize_windows(windows: list[int] | None) -> list[int]:
    values = list(windows or DEFAULT_ANALYST_MENTION_WINDOWS)
    if not values:
        raise ValueError("windows 不能为空")
    if any(value < 1 or value > 30 for value in values):
        raise ValueError("window 必须在 1 到 30 之间")
    return sorted(set(values))


def _validate_inputs(
    lookback_days: int,
    cooldown_trade_days: int,
    benchmark_ts_code: str,
    start_time: datetime | None,
    end_time: datetime | None,
) -> None:
    if lookback_days < 1:
        raise ValueError("lookback_days 必须大于 0")
    if cooldown_trade_days < 0:
        raise ValueError("cooldown_trade_days 不能小于 0")
    if not benchmark_ts_code:
        raise ValueError("benchmark_ts_code 不能为空")
    if (start_time is None) != (end_time is None):
        raise ValueError("start_time 和 end_time 必须同时提供")
    if start_time is not None and end_time is not None and end_time <= start_time:
        raise ValueError("end_time 必须晚于 start_time")


def _metadata(
    *,
    as_of: date,
    lookback_days: int,
    start_time: datetime,
    end_time: datetime,
    windows: list[int],
    source: MessageSource | None,
    cooldown_trade_days: int,
    remote_price_fetch: bool,
    extractor_version: str,
    benchmark_ts_code: str,
) -> dict[str, object]:
    return {
        "as_of": as_of.isoformat(),
        "lookback_days": lookback_days,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "windows": windows,
        "source": source,
        "cooldown_trade_days": cooldown_trade_days,
        "remote_price_fetch": remote_price_fetch,
        "extractor_version": extractor_version,
        "benchmark_ts_code": benchmark_ts_code,
    }


def _result(
    *,
    run_id: str,
    as_of: date,
    start_time: datetime,
    end_time: datetime,
    windows: list[int],
    benchmark_ts_code: str,
    extractor_version: str,
    scanned_count: int,
    stock_hit_count: int,
    raw_count: int,
    source_broker_filtered_count: int,
    broad_list_count: int,
    inserted_count: int,
    effective_count: int,
    repeated_count: int,
    stats: dict[str, int],
) -> AnalystMentionRefreshResult:
    return AnalystMentionRefreshResult(
        run_id=run_id,
        as_of=as_of,
        start_time=start_time,
        end_time=end_time,
        windows=windows,
        benchmark_ts_code=benchmark_ts_code,
        extractor_version=extractor_version,
        scanned_message_count=scanned_count,
        stock_hit_message_count=stock_hit_count,
        raw_mention_count=raw_count,
        source_broker_filtered_count=source_broker_filtered_count,
        broad_list_mention_count=broad_list_count,
        inserted_mention_count=inserted_count,
        effective_mention_count=effective_count,
        repeated_mention_count=repeated_count,
        **stats,
    )


def _run_error(exc: BaseException) -> BaseException:
    if isinstance(exc, KeyboardInterrupt):
        return RuntimeError("任务被中断")
    return exc


def _date_key(value: date) -> str:
    return value.strftime("%Y%m%d")
