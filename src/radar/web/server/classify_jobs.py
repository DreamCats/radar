from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Lock

from radar.core.config import RadarConfig
from radar.core.models import MessageSource
from radar.core.runs import RunRecord, fail_run, fail_stale_runs, list_runs, start_run
from radar.core.usecases import classify_messages_range
from radar.web.server.schemas import ClassifyMessagesJobItem, ClassifyMessagesRequest

CLASSIFY_RUN_KIND = "message_classify_range"
STALE_AFTER = timedelta(hours=4)

_SOURCE_MAP: dict[str, MessageSource | None] = {
    "all": None,
    "personal_message": "个人消息",
    "group_message": "个人群",
}
_SOURCE_LABELS: dict[str, str] = {
    "all": "全部",
    "personal_message": "个人消息",
    "group_message": "个人群",
}

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="radar-classify")
_SUBMIT_LOCK = Lock()


def submit_classify_messages_job(config: RadarConfig, request: ClassifyMessagesRequest) -> list[ClassifyMessagesJobItem]:
    with _SUBMIT_LOCK:
        mark_stale_classify_runs(config)

        running = _running_classify_run(config)
        if running is not None:
            return [_job_item_from_run(running)]

        target = _classify_target(request)
        run_id = start_run(
            config.database_path,
            kind=CLASSIFY_RUN_KIND,
            target=target,
            metadata=_classify_metadata(config, request),
        )
        _EXECUTOR.submit(_run_classify_messages_job, config, request, run_id)
        return [
            ClassifyMessagesJobItem(
                source_key=request.source,
                source=_SOURCE_LABELS[request.source],
                run_id=run_id,
                reused_existing=False,
                status="running",
            )
        ]


def mark_stale_classify_runs(config: RadarConfig) -> int:
    return fail_stale_runs(config.database_path, older_than=datetime.now() - STALE_AFTER, kind=CLASSIFY_RUN_KIND)


def _run_classify_messages_job(config: RadarConfig, request: ClassifyMessagesRequest, run_id: str) -> None:
    try:
        classify_messages_range(
            config,
            source=_SOURCE_MAP[request.source],
            start_time=request.start_time,
            end_time=request.end_time,
            chunk_hours=request.chunk_hours,
            limit=request.limit,
            force=request.force,
            use_llm=True,
            provider_name=request.provider_name,
            provider_names=_provider_names(config, request),
            batch_size=request.batch_size,
            max_concurrency=request.max_concurrency,
            retry=request.retry,
            low_confidence_threshold=request.low_confidence_threshold,
            run_id=run_id,
        )
    except Exception as exc:
        fail_run(config.database_path, run_id, exc)


def _classify_target(request: ClassifyMessagesRequest) -> str:
    mode = request.retry or ("force" if request.force else "missing")
    return (
        f"{request.source}:{request.start_time.isoformat()}..{request.end_time.isoformat()}"
        f"|mode={mode}|threshold={request.low_confidence_threshold}"
    )


def _classify_metadata(config: RadarConfig, request: ClassifyMessagesRequest) -> dict[str, object]:
    return {
        "source": request.source,
        "start_time": request.start_time.isoformat(),
        "end_time": request.end_time.isoformat(),
        "force": request.force,
        "chunk_hours": request.chunk_hours,
        "limit": request.limit,
        "batch_size": request.batch_size,
        "max_concurrency": request.max_concurrency,
        "provider_name": request.provider_name,
        "provider_names": request.provider_names,
        "effective_provider_names": _provider_names(config, request),
        "retry": request.retry,
        "low_confidence_threshold": request.low_confidence_threshold,
    }


def _running_classify_run(config: RadarConfig) -> RunRecord | None:
    runs = list_runs(config.database_path, kind=CLASSIFY_RUN_KIND, status="running", limit=1)
    return runs[0] if runs else None


def _job_item_from_run(run: RunRecord) -> ClassifyMessagesJobItem:
    source_key = run.metadata.get("source")
    if not isinstance(source_key, str) or source_key not in _SOURCE_LABELS:
        source_key = "all"
    return ClassifyMessagesJobItem(
        source_key=source_key,
        source=_SOURCE_LABELS[source_key],
        run_id=run.run_id,
        reused_existing=True,
        status="running",
    )


def _provider_names(config: RadarConfig, request: ClassifyMessagesRequest) -> list[str] | None:
    return _provider_names_from_config(request, list(config.llm.providers))


def _provider_names_from_config(
    request: ClassifyMessagesRequest,
    configured_names: list[str] | None,
) -> list[str] | None:
    if request.provider_name:
        return request.provider_names
    if request.provider_names:
        return request.provider_names
    return configured_names or None
