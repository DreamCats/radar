from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from radar.core.config import RadarConfig
from radar.core.scheduler import ScheduleRecord, resolve_window_preset
from radar.core.storage import list_runs
from radar.core.usecases.analyst_mentions.refresh import ANALYST_MENTION_RUN_KIND
from radar.web.server.backtest_jobs import mark_stale_analyst_backtest_runs, submit_analyst_backtest_job
from radar.web.server.catalyst_strategy_jobs import (
    CATALYST_STRATEGY_RUN_KIND,
    mark_stale_catalyst_strategy_runs,
    submit_catalyst_strategy_job,
)
from radar.web.server.ingest_jobs import INGEST_RUN_KIND, mark_stale_ingest_runs, submit_wechat_ingest_jobs
from radar.web.server.market_stock_jobs import (
    MARKET_STOCK_REFRESH_RUN_KIND,
    mark_stale_market_stock_refresh_runs,
    submit_market_stock_refresh_job,
)
from radar.web.server.schemas import (
    AnalystBacktestRequest,
    CatalystStrategyJobRequest,
    IngestWechatRequest,
    MarketStockRefreshRequest,
)


@dataclass(frozen=True)
class PreparedScheduleJob:
    request_model: object
    request_payload: dict[str, Any]


@dataclass(frozen=True)
class SubmittedScheduleJob:
    run_ids: list[str]
    reused_existing: bool


RUN_KINDS_BY_JOB_KEY: dict[str, tuple[str, ...]] = {
    "wechat_ingest": (INGEST_RUN_KIND,),
    "analyst_backtest": (ANALYST_MENTION_RUN_KIND,),
    "market_stock_refresh": (MARKET_STOCK_REFRESH_RUN_KIND,),
    "catalyst_strategy": (CATALYST_STRATEGY_RUN_KIND,),
}


def has_running_scheduled_job(config: RadarConfig, schedule: ScheduleRecord) -> bool:
    for kind in RUN_KINDS_BY_JOB_KEY.get(schedule.job_key, ()):
        if list_runs(config.database_path, kind=kind, status="running", limit=1):
            return True
    return False


def mark_stale_scheduled_runs(config: RadarConfig, schedule: ScheduleRecord) -> int:
    if schedule.job_key == "wechat_ingest":
        return mark_stale_ingest_runs(config)
    if schedule.job_key == "analyst_backtest":
        return mark_stale_analyst_backtest_runs(config)
    if schedule.job_key == "market_stock_refresh":
        return mark_stale_market_stock_refresh_runs(config)
    if schedule.job_key == "catalyst_strategy":
        return mark_stale_catalyst_strategy_runs(config)
    return 0


def prepare_schedule_job(schedule: ScheduleRecord, *, now: datetime) -> PreparedScheduleJob:
    payload = dict(schedule.request)
    start_time, end_time = resolve_window_preset(schedule.window_preset, now)
    if start_time is not None and end_time is not None:
        payload["start_time"] = start_time
        payload["end_time"] = end_time

    if schedule.job_key == "wechat_ingest":
        request = IngestWechatRequest(**payload)
    elif schedule.job_key == "analyst_backtest":
        payload.setdefault("as_of", now.date())
        request = AnalystBacktestRequest(**payload)
    elif schedule.job_key == "market_stock_refresh":
        payload.setdefault("force", True)
        request = MarketStockRefreshRequest(**payload)
    elif schedule.job_key == "catalyst_strategy":
        request = CatalystStrategyJobRequest(**payload)
    else:
        raise ValueError(f"未知定时作业: {schedule.job_key}")

    return PreparedScheduleJob(
        request_model=request,
        request_payload=request.model_dump(mode="json"),
    )


def submit_prepared_schedule_job(
    config: RadarConfig,
    schedule: ScheduleRecord,
    prepared: PreparedScheduleJob,
) -> SubmittedScheduleJob:
    if schedule.job_key == "wechat_ingest":
        items = submit_wechat_ingest_jobs(config, _typed(prepared.request_model, IngestWechatRequest))
    elif schedule.job_key == "analyst_backtest":
        item = submit_analyst_backtest_job(config, _typed(prepared.request_model, AnalystBacktestRequest))
        items = [item]
    elif schedule.job_key == "market_stock_refresh":
        item = submit_market_stock_refresh_job(config, _typed(prepared.request_model, MarketStockRefreshRequest))
        items = [item]
    elif schedule.job_key == "catalyst_strategy":
        item = submit_catalyst_strategy_job(config, _typed(prepared.request_model, CatalystStrategyJobRequest))
        items = [item]
    else:
        raise ValueError(f"未知定时作业: {schedule.job_key}")

    return SubmittedScheduleJob(
        run_ids=[item.run_id for item in items],
        reused_existing=any(item.reused_existing for item in items),
    )


def _typed(value: object, expected_type):
    if not isinstance(value, expected_type):
        raise TypeError(f"调度请求类型不匹配: expected={expected_type.__name__}")
    return value
