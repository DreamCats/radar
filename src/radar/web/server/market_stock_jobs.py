from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Lock

from radar.core.config import RadarConfig
from radar.core.storage import fail_run, fail_stale_runs, finish_run, get_running_run, start_run
from radar.core.tushare import refresh_stock_master
from radar.web.server.job_locks import WRITE_JOB_LOCK
from radar.web.server.schemas import DerivedJobItem, MarketStockRefreshRequest

MARKET_STOCK_REFRESH_RUN_KIND = "market_stock_master_refresh"
MARKET_STOCK_REFRESH_TARGET = "stocks:full"
STALE_AFTER = timedelta(hours=2)

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="radar-market-stocks")
_SUBMIT_LOCK = Lock()


def submit_market_stock_refresh_job(config: RadarConfig, request: MarketStockRefreshRequest) -> DerivedJobItem:
    with _SUBMIT_LOCK:
        mark_stale_market_stock_refresh_runs(config)
        running = get_running_run(
            config.database_path,
            kind=MARKET_STOCK_REFRESH_RUN_KIND,
            target=MARKET_STOCK_REFRESH_TARGET,
        )
        if running is not None:
            return DerivedJobItem(
                job_type="market_stock_refresh",
                run_id=running.run_id,
                reused_existing=True,
                status="running",
            )

        run_id = start_run(
            config.database_path,
            kind=MARKET_STOCK_REFRESH_RUN_KIND,
            target=MARKET_STOCK_REFRESH_TARGET,
            metadata=_metadata(request),
        )
        _EXECUTOR.submit(_run_market_stock_refresh_job, config, request, run_id)
        return DerivedJobItem(
            job_type="market_stock_refresh",
            run_id=run_id,
            reused_existing=False,
            status="running",
        )


def mark_stale_market_stock_refresh_runs(config: RadarConfig) -> int:
    return fail_stale_runs(
        config.database_path,
        older_than=datetime.now() - STALE_AFTER,
        kind=MARKET_STOCK_REFRESH_RUN_KIND,
    )


def _run_market_stock_refresh_job(config: RadarConfig, request: MarketStockRefreshRequest, run_id: str) -> None:
    with WRITE_JOB_LOCK:
        try:
            result = refresh_stock_master(config, force=request.force)
            finish_run(
                config.database_path,
                run_id,
                raw_count=result.fetched_count,
                stored_count=result.stored_count,
                filtered_count=result.fetched_count - result.stored_count,
                metadata=_metadata(request) | result.metadata(),
            )
        except BaseException as exc:
            fail_run(config.database_path, run_id, exc)


def _metadata(request: MarketStockRefreshRequest) -> dict[str, object]:
    return request.model_dump(mode="json")
