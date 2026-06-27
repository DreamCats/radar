from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Lock

from radar.core.config import RadarConfig
from radar.core.storage import fail_run, fail_stale_runs, get_running_run, start_run
from radar.core.usecases.ingest_wechat import ingest_range_metadata, ingest_range_target, ingest_wechat_range
from radar.web.server.job_locks import WRITE_JOB_LOCK
from radar.web.server.schemas import IngestWechatJobItem, IngestWechatRequest

INGEST_RUN_KIND = "wechat_ingest_range"
STALE_AFTER = timedelta(hours=1)
SUBMIT_SQLITE_TIMEOUT_SECONDS = 3.0
SUBMIT_SQLITE_BUSY_TIMEOUT_MS = 3_000

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="radar-ingest")
_SUBMIT_LOCK = Lock()


class JobSubmissionBusyError(RuntimeError):
    pass


def submit_wechat_ingest_jobs(config: RadarConfig, request: IngestWechatRequest) -> list[IngestWechatJobItem]:
    try:
        with _SUBMIT_LOCK:
            mark_stale_ingest_runs(
                config,
                timeout_seconds=SUBMIT_SQLITE_TIMEOUT_SECONDS,
                busy_timeout_ms=SUBMIT_SQLITE_BUSY_TIMEOUT_MS,
            )

            source_keys = list(config.wechat.sources) if request.source == "all" else [request.source]
            items: list[IngestWechatJobItem] = []
            for source_key in source_keys:
                source = config.wechat.sources[source_key].name
                target = ingest_range_target(source_key, request.start_time, request.end_time)
                running = get_running_run(
                    config.database_path,
                    kind=INGEST_RUN_KIND,
                    target=target,
                    timeout_seconds=SUBMIT_SQLITE_TIMEOUT_SECONDS,
                    busy_timeout_ms=SUBMIT_SQLITE_BUSY_TIMEOUT_MS,
                )
                if running is not None:
                    items.append(
                        IngestWechatJobItem(
                            source_key=source_key,
                            source=source,
                            run_id=running.run_id,
                            reused_existing=True,
                            status=running.status,
                        )
                    )
                    continue

                run_id = start_run(
                    config.database_path,
                    kind=INGEST_RUN_KIND,
                    target=target,
                    metadata=ingest_range_metadata(
                        config,
                        source_key=source_key,
                        start_time=request.start_time,
                        end_time=request.end_time,
                        force=request.force,
                        chunk_hours=request.chunk_hours,
                        concurrency=request.concurrency,
                    ),
                    timeout_seconds=SUBMIT_SQLITE_TIMEOUT_SECONDS,
                    busy_timeout_ms=SUBMIT_SQLITE_BUSY_TIMEOUT_MS,
                )
                _EXECUTOR.submit(_run_wechat_ingest_job, config, request, source_key, run_id)
                items.append(
                    IngestWechatJobItem(
                        source_key=source_key,
                        source=source,
                        run_id=run_id,
                        reused_existing=False,
                        status="running",
                    )
                )
            return items
    except sqlite3.OperationalError as exc:
        if _is_database_locked(exc):
            raise JobSubmissionBusyError("数据库正在写入，请稍后再提交") from exc
        raise


def mark_stale_ingest_runs(
    config: RadarConfig,
    *,
    timeout_seconds: float | None = None,
    busy_timeout_ms: int | None = None,
) -> int:
    return fail_stale_runs(
        config.database_path,
        older_than=datetime.now() - STALE_AFTER,
        kind=INGEST_RUN_KIND,
        timeout_seconds=timeout_seconds,
        busy_timeout_ms=busy_timeout_ms,
    )


def _run_wechat_ingest_job(config: RadarConfig, request: IngestWechatRequest, source_key: str, run_id: str) -> None:
    with WRITE_JOB_LOCK:
        try:
            ingest_wechat_range(
                config,
                source_key=source_key,
                start_time=request.start_time,
                end_time=request.end_time,
                force=request.force,
                chunk_hours=request.chunk_hours,
                concurrency=request.concurrency,
                run_id=run_id,
            )
        except Exception as exc:
            fail_run(config.database_path, run_id, exc)


def _is_database_locked(error: sqlite3.OperationalError) -> bool:
    message = str(error).lower()
    return "database is locked" in message or "database table is locked" in message
