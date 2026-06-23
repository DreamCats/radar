from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from radar.core.config import RadarConfig
from radar.core.scheduler import ScheduleRecord, resolve_window_preset
from radar.core.storage import list_runs
from radar.core.usecases.analyst_mentions.refresh import ANALYST_MENTION_RUN_KIND
from radar.web.server.backtest_jobs import mark_stale_analyst_backtest_runs, submit_analyst_backtest_job
from radar.web.server.classify_jobs import CLASSIFY_RUN_KIND, mark_stale_classify_runs, submit_classify_messages_job
from radar.web.server.ingest_jobs import INGEST_RUN_KIND, mark_stale_ingest_runs, submit_wechat_ingest_jobs
from radar.web.server.market_anchor_jobs import (
    ANCHOR_RUN_KIND,
    mark_stale_market_anchor_runs,
    submit_market_anchor_update_job,
)
from radar.web.server.schemas import (
    AnalystBacktestRequest,
    ClassifyMessagesRequest,
    IngestWechatRequest,
    MarketAnchorUpdateRequest,
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
    "message_classify": (CLASSIFY_RUN_KIND,),
    "market_anchor_update": (ANCHOR_RUN_KIND,),
    "analyst_backtest": (ANALYST_MENTION_RUN_KIND,),
}


def has_running_scheduled_job(config: RadarConfig, schedule: ScheduleRecord) -> bool:
    for kind in RUN_KINDS_BY_JOB_KEY.get(schedule.job_key, ()):
        if list_runs(config.database_path, kind=kind, status="running", limit=1):
            return True
    return False


def mark_stale_scheduled_runs(config: RadarConfig, schedule: ScheduleRecord) -> int:
    if schedule.job_key == "wechat_ingest":
        return mark_stale_ingest_runs(config)
    if schedule.job_key == "message_classify":
        return mark_stale_classify_runs(config)
    if schedule.job_key == "market_anchor_update":
        return mark_stale_market_anchor_runs(config)
    if schedule.job_key == "analyst_backtest":
        return mark_stale_analyst_backtest_runs(config)
    return 0


def prepare_schedule_job(schedule: ScheduleRecord, *, now: datetime) -> PreparedScheduleJob:
    payload = dict(schedule.request)
    start_time, end_time = resolve_window_preset(schedule.window_preset, now)
    if start_time is not None and end_time is not None:
        payload["start_time"] = start_time
        payload["end_time"] = end_time

    if schedule.job_key == "wechat_ingest":
        request = IngestWechatRequest(**payload)
    elif schedule.job_key == "message_classify":
        request = ClassifyMessagesRequest(**payload)
    elif schedule.job_key == "market_anchor_update":
        payload.setdefault("trade_date", _trade_date(now))
        request = MarketAnchorUpdateRequest(**payload)
    elif schedule.job_key == "analyst_backtest":
        payload.setdefault("as_of", now.date())
        request = AnalystBacktestRequest(**payload)
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
    elif schedule.job_key == "message_classify":
        items = submit_classify_messages_job(config, _typed(prepared.request_model, ClassifyMessagesRequest))
    elif schedule.job_key == "market_anchor_update":
        item = submit_market_anchor_update_job(config, _typed(prepared.request_model, MarketAnchorUpdateRequest))
        items = [item]
    elif schedule.job_key == "analyst_backtest":
        item = submit_analyst_backtest_job(config, _typed(prepared.request_model, AnalystBacktestRequest))
        items = [item]
    else:
        raise ValueError(f"未知定时作业: {schedule.job_key}")

    return SubmittedScheduleJob(
        run_ids=[item.run_id for item in items],
        reused_existing=any(item.reused_existing for item in items),
    )


def _trade_date(value: datetime) -> str:
    return date(value.year, value.month, value.day).strftime("%Y%m%d")


def _typed(value: object, expected_type):
    if not isinstance(value, expected_type):
        raise TypeError(f"调度请求类型不匹配: expected={expected_type.__name__}")
    return value
