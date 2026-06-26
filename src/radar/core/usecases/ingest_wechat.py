from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock
from time import sleep

import httpx
from pydantic import BaseModel

from radar.core.config import RadarConfig
from radar.core.wechat.fetch import fetch_messages
from radar.core.wechat.filtering import is_group_blacklisted
from radar.core.models import MessageSource, RawMessage
from radar.core.storage import fail_run, finish_run, start_run, update_run_progress
from radar.core.storage import (
    connect,
    fetch_window_covered,
    init_db,
    record_fetch_window,
    upsert_messages,
)
from radar.core.usecases.time_windows import time_chunks

FetchMessages = Callable[[str, MessageSource, datetime, datetime, float], list[RawMessage]]
ProgressUpdate = Callable[[dict[str, object]], None]
_WRITE_LOCK = Lock()


class IngestWindowResult(BaseModel):
    source_key: str
    source: MessageSource
    start_time: datetime
    end_time: datetime
    skipped_existing: bool = False
    raw_count: int = 0
    filtered_count: int = 0
    stored_count: int = 0
    run_id: str | None = None


class IngestRangeResult(BaseModel):
    source_key: str
    source: MessageSource
    start_time: datetime
    end_time: datetime
    chunk_count: int = 0
    skipped_count: int = 0
    raw_count: int = 0
    filtered_count: int = 0
    stored_count: int = 0
    failed_count: int = 0
    run_id: str | None = None


@dataclass(frozen=True)
class FetchChunkResult:
    start_time: datetime
    end_time: datetime
    raw_messages: list[RawMessage]
    attempts: int


@dataclass(frozen=True)
class ChunkWriteResult:
    raw_count: int
    filtered_count: int
    stored_count: int


@dataclass(frozen=True)
class FetchAndWriteResult:
    fetched_chunk_count: int
    written_chunk_count: int
    failed_chunks: list[dict[str, object]]
    retry_count: int
    raw_count: int
    filtered_count: int
    stored_count: int


class ChunkFetchError(Exception):
    def __init__(self, start_time: datetime, end_time: datetime, attempts: int, error: BaseException) -> None:
        super().__init__(str(error))
        self.start_time = start_time
        self.end_time = end_time
        self.attempts = attempts
        self.original_error = error


def ingest_wechat_window(
    config: RadarConfig,
    *,
    source_key: str,
    start_time: datetime,
    end_time: datetime,
    force: bool = False,
    fetcher: FetchMessages | None = None,
) -> IngestWindowResult:
    """拉取一个微信时间窗并写入 SQLite；重复窗口默认跳过。"""

    source_config = config.wechat.sources[source_key]
    source = source_config.name
    start_text = start_time.isoformat()
    end_text = end_time.isoformat()
    run_metadata = _run_metadata(
        source_key=source_key,
        source=source,
        start_time=start_time,
        end_time=end_time,
        force=force,
    )
    run_id = start_run(
        config.database_path,
        kind="wechat_ingest_window",
        target=_run_target(source_key, start_time, end_time),
        metadata=run_metadata,
    )

    conn = connect(config.database_path)
    try:
        init_db(conn)
        if not force and fetch_window_covered(
            conn,
            source=source,
            start_time=start_text,
            end_time=end_text,
        ):
            finish_run(config.database_path, run_id, status="skipped", metadata=run_metadata)
            return IngestWindowResult(
                source_key=source_key,
                source=source,
                start_time=start_time,
                end_time=end_time,
                skipped_existing=True,
                run_id=run_id,
            )

        fetch_messages_fn = fetcher or _default_fetcher
        raw_messages = fetch_messages_fn(
            config.wechat_endpoint_url(source_key),
            source,
            start_time,
            end_time,
            config.wechat.timeout,
        )
        messages = [
            message
            for message in raw_messages
            if not is_group_blacklisted(message.group_name, config.filters.group_blacklist_patterns)
        ]
        stored_count = upsert_messages(conn, messages)
        filtered_count = len(raw_messages) - len(messages)
        record_fetch_window(
            conn,
            source=source,
            start_time=start_text,
            end_time=end_text,
            fetched_at=datetime.now().isoformat(),
            raw_count=len(raw_messages),
            stored_count=stored_count,
            filtered_count=filtered_count,
        )
        finish_run(
            config.database_path,
            run_id,
            raw_count=len(raw_messages),
            stored_count=stored_count,
            filtered_count=filtered_count,
            metadata=run_metadata,
        )
        return IngestWindowResult(
            source_key=source_key,
            source=source,
            start_time=start_time,
            end_time=end_time,
            raw_count=len(raw_messages),
            filtered_count=filtered_count,
            stored_count=stored_count,
            run_id=run_id,
        )
    except Exception as exc:
        _safe_fail_run(config, run_id, exc)
        raise
    finally:
        conn.close()


def ingest_wechat_range(
    config: RadarConfig,
    *,
    source_key: str,
    start_time: datetime,
    end_time: datetime,
    chunk_hours: int = 1,
    concurrency: int = 4,
    force: bool = False,
    fetcher: FetchMessages | None = None,
    run_id: str | None = None,
) -> IngestRangeResult:
    """按时间切片并发拉取，随后串行写库，避免 SQLite 并发写锁竞争。"""

    if chunk_hours < 1:
        raise ValueError("chunk_hours 必须大于 0")
    if concurrency < 1:
        raise ValueError("concurrency 必须大于 0")

    source_config = config.wechat.sources[source_key]
    source = source_config.name
    run_metadata = _run_metadata(
        source_key=source_key,
        source=source,
        start_time=start_time,
        end_time=end_time,
        force=force,
        chunk_hours=chunk_hours,
        concurrency=concurrency,
    )
    if run_id is None:
        run_id = start_run(
            config.database_path,
            kind="wechat_ingest_range",
            target=ingest_range_target(source_key, start_time, end_time),
            metadata=run_metadata,
        )
    chunks = time_chunks(start_time, end_time, timedelta(hours=chunk_hours))
    try:
        pending_chunks, skipped_count = _pending_chunks(config, source, chunks, force)
        update_run_progress(
            config.database_path,
            run_id,
            metadata={
                "stage": "准备拉取",
                "chunk_count": len(chunks),
                "pending_chunk_count": len(pending_chunks),
                "skipped_count": skipped_count,
                "fetched_chunk_count": 0,
                "written_chunk_count": 0,
            },
        )
        chunk_result = _fetch_and_write_chunks(
            config,
            source_key,
            source,
            pending_chunks,
            concurrency,
            fetcher,
            progress=lambda metadata: update_run_progress(config.database_path, run_id, metadata=metadata),
        )
        raw_count = chunk_result.raw_count
        filtered_count = chunk_result.filtered_count
        stored_count = chunk_result.stored_count
        failed_chunks = chunk_result.failed_chunks
        if failed_chunks and not (chunk_result.written_chunk_count or skipped_count):
            error_message = _failed_chunks_summary(failed_chunks)
            _safe_fail_run(config, run_id, RuntimeError(error_message))
            raise RuntimeError(error_message)

        if failed_chunks:
            status = "partial_failed"
            error_message = _failed_chunks_summary(failed_chunks)
        else:
            status = "skipped" if skipped_count == len(chunks) else "succeeded"
            error_message = None
        final_metadata = run_metadata | {
            "chunk_count": len(chunks),
            "pending_chunk_count": len(pending_chunks),
            "skipped_count": skipped_count,
            "fetched_chunk_count": chunk_result.fetched_chunk_count,
            "written_chunk_count": chunk_result.written_chunk_count,
            "failed_chunk_count": len(failed_chunks),
            "failed_chunks": failed_chunks,
            "retry_count": chunk_result.retry_count,
        }
        finish_run(
            config.database_path,
            run_id,
            status=status,
            raw_count=raw_count,
            stored_count=stored_count,
            filtered_count=filtered_count,
            error_message=error_message,
            metadata=final_metadata,
        )

        return IngestRangeResult(
            source_key=source_key,
            source=source,
            start_time=start_time,
            end_time=end_time,
            chunk_count=len(chunks),
            skipped_count=skipped_count,
            raw_count=raw_count,
            filtered_count=filtered_count,
            stored_count=stored_count,
            failed_count=len(failed_chunks),
            run_id=run_id,
        )
    except Exception as exc:
        _safe_fail_run(config, run_id, exc)
        raise


def _default_fetcher(
    base_url: str,
    source: MessageSource,
    start_time: datetime,
    end_time: datetime,
    timeout: float,
) -> list[RawMessage]:
    return fetch_messages(
        base_url,
        source=source,
        start_time=start_time,
        end_time=end_time,
        timeout=timeout,
    )


def _pending_chunks(
    config: RadarConfig,
    source: MessageSource,
    chunks: list[tuple[datetime, datetime]],
    force: bool,
) -> tuple[list[tuple[datetime, datetime]], int]:
    if force:
        return chunks, 0

    conn = connect(config.database_path)
    try:
        init_db(conn)
        pending: list[tuple[datetime, datetime]] = []
        skipped_count = 0
        for chunk_start, chunk_end in chunks:
            if fetch_window_covered(
                conn,
                source=source,
                start_time=chunk_start.isoformat(),
                end_time=chunk_end.isoformat(),
            ):
                skipped_count += 1
            else:
                pending.append((chunk_start, chunk_end))
        return pending, skipped_count
    finally:
        conn.close()


def _fetch_and_write_chunks(
    config: RadarConfig,
    source_key: str,
    source: MessageSource,
    chunks: list[tuple[datetime, datetime]],
    concurrency: int,
    fetcher: FetchMessages | None,
    progress: ProgressUpdate | None = None,
) -> FetchAndWriteResult:
    fetch_messages_fn = fetcher or _default_fetcher
    base_url = config.wechat_endpoint_url(source_key)
    max_workers = min(concurrency, len(chunks)) or 1

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _fetch_chunk_with_retries,
                config,
                fetch_messages_fn,
                base_url,
                source,
                chunk_start,
                chunk_end,
                config.wechat.timeout,
            ): (chunk_start, chunk_end)
            for chunk_start, chunk_end in chunks
        }
        fetched_chunk_count = 0
        written_chunk_count = 0
        failed_chunks: list[dict[str, object]] = []
        retry_count = 0
        raw_count = 0
        filtered_count = 0
        stored_count = 0
        for future in as_completed(futures):
            chunk_start, chunk_end = futures[future]
            try:
                fetched = future.result()
            except ChunkFetchError as exc:
                retry_count += max(0, exc.attempts - 1)
                failed_chunks.append(_failed_chunk_metadata(exc))
                if progress is not None:
                    progress(
                        {
                            "stage": "部分分片失败",
                            "pending_chunk_count": len(chunks),
                            "fetched_chunk_count": fetched_chunk_count,
                            "written_chunk_count": written_chunk_count,
                            "failed_chunk_count": len(failed_chunks),
                            "retry_count": retry_count,
                            "failed_chunks": failed_chunks,
                            "current_chunk_start": chunk_start.isoformat(),
                            "current_chunk_end": chunk_end.isoformat(),
                        }
                    )
                continue

            fetched_chunk_count += 1
            retry_count += max(0, fetched.attempts - 1)
            written = _write_chunk(config, source, fetched.start_time, fetched.end_time, fetched.raw_messages)
            written_chunk_count += 1
            raw_count += written.raw_count
            filtered_count += written.filtered_count
            stored_count += written.stored_count
            if progress is not None:
                progress(
                    {
                        "stage": "写入数据中",
                        "pending_chunk_count": len(chunks),
                        "fetched_chunk_count": fetched_chunk_count,
                        "written_chunk_count": written_chunk_count,
                        "failed_chunk_count": len(failed_chunks),
                        "retry_count": retry_count,
                        "raw_count": raw_count,
                        "filtered_count": filtered_count,
                        "stored_count": stored_count,
                        "current_chunk_start": fetched.start_time.isoformat(),
                        "current_chunk_end": fetched.end_time.isoformat(),
                    }
                )
    return FetchAndWriteResult(
        fetched_chunk_count=fetched_chunk_count,
        written_chunk_count=written_chunk_count,
        failed_chunks=failed_chunks,
        retry_count=retry_count,
        raw_count=raw_count,
        filtered_count=filtered_count,
        stored_count=stored_count,
    )


def _fetch_chunk_with_retries(
    config: RadarConfig,
    fetch_messages_fn: FetchMessages,
    base_url: str,
    source: MessageSource,
    chunk_start: datetime,
    chunk_end: datetime,
    timeout: float,
) -> FetchChunkResult:
    attempts = max(1, config.wechat.retry_attempts)
    for attempt in range(1, attempts + 1):
        try:
            raw_messages = fetch_messages_fn(base_url, source, chunk_start, chunk_end, timeout)
            return FetchChunkResult(chunk_start, chunk_end, raw_messages, attempt)
        except Exception as exc:
            if attempt >= attempts or not _is_retryable_fetch_error(exc):
                raise ChunkFetchError(chunk_start, chunk_end, attempt, exc) from exc
            delay = min(
                config.wechat.retry_backoff_seconds * (2 ** (attempt - 1)),
                config.wechat.retry_max_backoff_seconds,
            )
            if delay > 0:
                sleep(delay)
    raise RuntimeError("unreachable")


def _is_retryable_fetch_error(error: BaseException) -> bool:
    if isinstance(error, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError)):
        return True
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in {502, 503, 504}
    return False


def _write_chunk(
    config: RadarConfig,
    source: MessageSource,
    chunk_start: datetime,
    chunk_end: datetime,
    raw_messages: list[RawMessage],
) -> ChunkWriteResult:
    with _WRITE_LOCK:
        conn = connect(config.database_path)
        try:
            init_db(conn)
            # 黑名单过滤在写库前完成，避免明显非投研群进入主表和 FTS。
            messages = [
                message
                for message in raw_messages
                if not is_group_blacklisted(message.group_name, config.filters.group_blacklist_patterns)
            ]
            chunk_filtered_count = len(raw_messages) - len(messages)
            chunk_stored_count = upsert_messages(conn, messages)
            record_fetch_window(
                conn,
                source=source,
                start_time=chunk_start.isoformat(),
                end_time=chunk_end.isoformat(),
                fetched_at=datetime.now().isoformat(),
                raw_count=len(raw_messages),
                stored_count=chunk_stored_count,
                filtered_count=chunk_filtered_count,
            )
            return ChunkWriteResult(
                raw_count=len(raw_messages),
                filtered_count=chunk_filtered_count,
                stored_count=chunk_stored_count,
            )
        finally:
            conn.close()


def _failed_chunk_metadata(error: ChunkFetchError) -> dict[str, object]:
    return {
        "start_time": error.start_time.isoformat(),
        "end_time": error.end_time.isoformat(),
        "attempts": error.attempts,
        "error": str(error.original_error)[:500],
    }


def _failed_chunks_summary(failed_chunks: list[dict[str, object]]) -> str:
    first = failed_chunks[0]
    return (
        f"{len(failed_chunks)} 个分片拉取失败，首个失败 "
        f"{first.get('start_time')}..{first.get('end_time')}: {first.get('error')}"
    )


def _run_target(source_key: str, start_time: datetime, end_time: datetime) -> str:
    return f"{source_key}:{start_time.isoformat()}..{end_time.isoformat()}"


def ingest_range_target(source_key: str, start_time: datetime, end_time: datetime) -> str:
    return _run_target(source_key, start_time, end_time)


def ingest_range_metadata(
    config: RadarConfig,
    *,
    source_key: str,
    start_time: datetime,
    end_time: datetime,
    force: bool,
    chunk_hours: int,
    concurrency: int,
) -> dict[str, object]:
    source = config.wechat.sources[source_key].name
    return _run_metadata(
        source_key=source_key,
        source=source,
        start_time=start_time,
        end_time=end_time,
        force=force,
        chunk_hours=chunk_hours,
        concurrency=concurrency,
    )


def _run_metadata(
    *,
    source_key: str,
    source: MessageSource,
    start_time: datetime,
    end_time: datetime,
    force: bool,
    chunk_hours: int | None = None,
    concurrency: int | None = None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "source_key": source_key,
        "source": source,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "force": force,
    }
    if chunk_hours is not None:
        metadata["chunk_hours"] = chunk_hours
    if concurrency is not None:
        metadata["concurrency"] = concurrency
    return metadata


def _safe_fail_run(config: RadarConfig, run_id: str, error: BaseException) -> None:
    try:
        fail_run(config.database_path, run_id, error)
    except Exception:
        # 不能让审计写入失败覆盖真正的 ingest 异常。
        return
