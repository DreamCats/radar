from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Lock

from radar.core.config import RadarConfig
from radar.core.models import MessageSource
from radar.core.storage import fail_run, fail_stale_runs, get_running_run, start_run
from radar.core.usecases.analyst_mentions import ANALYST_MENTION_EXTRACTOR_VERSION, refresh_analyst_stock_mentions
from radar.core.usecases.analyst_mentions.refresh import ANALYST_MENTION_RUN_KIND
from radar.web.server.schemas import AnalystBacktestRequest, DerivedJobItem

STALE_AFTER = timedelta(hours=12)

_SOURCE_MAP: dict[str, MessageSource | None] = {
    "all": None,
    "personal_message": "个人消息",
    "group_message": "个人群",
}

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="radar-backtest")
_SUBMIT_LOCK = Lock()


def submit_analyst_backtest_job(config: RadarConfig, request: AnalystBacktestRequest) -> DerivedJobItem:
    with _SUBMIT_LOCK:
        mark_stale_analyst_backtest_runs(config)
        target = _analyst_target(request)
        running = get_running_run(config.database_path, kind=ANALYST_MENTION_RUN_KIND, target=target)
        if running is not None:
            return DerivedJobItem(
                job_type="analyst_backtest",
                run_id=running.run_id,
                reused_existing=True,
                status="running",
            )

        run_id = start_run(
            config.database_path,
            kind=ANALYST_MENTION_RUN_KIND,
            target=target,
            metadata=_metadata(request),
        )
        _EXECUTOR.submit(_run_analyst_backtest_job, config, request, run_id)
        return DerivedJobItem(
            job_type="analyst_backtest",
            run_id=run_id,
            reused_existing=False,
            status="running",
        )


def mark_stale_analyst_backtest_runs(config: RadarConfig) -> int:
    return fail_stale_runs(
        config.database_path,
        older_than=datetime.now() - STALE_AFTER,
        kind=ANALYST_MENTION_RUN_KIND,
    )


def _run_analyst_backtest_job(config: RadarConfig, request: AnalystBacktestRequest, run_id: str) -> None:
    try:
        refresh_analyst_stock_mentions(
            config,
            as_of=request.as_of,
            lookback_days=request.lookback_days,
            start_time=request.start_time,
            end_time=request.end_time,
            windows=request.windows,
            source=_SOURCE_MAP[request.source],
            cooldown_trade_days=request.cooldown_trade_days,
            remote_price_fetch=request.remote_price_fetch,
            benchmark_ts_code=request.benchmark_ts_code,
            run_id=run_id,
        )
    except BaseException as exc:
        fail_run(config.database_path, run_id, exc)


def _analyst_target(request: AnalystBacktestRequest) -> str:
    windows = ",".join(str(item) for item in sorted(set(request.windows)))
    if request.start_time is not None and request.end_time is not None:
        window_target = f"{request.start_time.isoformat()}..{request.end_time.isoformat()}"
    else:
        window_target = f"as_of={request.as_of.isoformat()}:days={request.lookback_days}"
    return (
        f"{request.source}:{window_target}:"
        f"windows={windows}|benchmark={request.benchmark_ts_code}"
        f"|cooldown={request.cooldown_trade_days}"
        f"|remote_prices={request.remote_price_fetch}"
        f"|extractor={ANALYST_MENTION_EXTRACTOR_VERSION}"
    )


def _metadata(request: AnalystBacktestRequest) -> dict[str, object]:
    return request.model_dump(mode="json") | {"extractor_version": ANALYST_MENTION_EXTRACTOR_VERSION}
