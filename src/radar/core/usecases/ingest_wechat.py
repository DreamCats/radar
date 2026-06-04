from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from pydantic import BaseModel

from radar.core.config import RadarConfig
from radar.core.fetch import fetch_messages
from radar.core.filtering import is_group_blacklisted
from radar.core.models import MessageSource, RawMessage
from radar.core.runs import fail_run, finish_run, start_run
from radar.core.store import (
    connect,
    fetch_window_covered,
    init_db,
    record_fetch_window,
    upsert_messages,
)

FetchMessages = Callable[[str, MessageSource, datetime, datetime, float], list[RawMessage]]


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
    run_id: str | None = None


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
    run_id = start_run(
        config.database_path,
        kind="wechat_ingest_range",
        target=_run_target(source_key, start_time, end_time),
        metadata=run_metadata,
    )
    chunks = _time_chunks(start_time, end_time, timedelta(hours=chunk_hours))
    try:
        pending_chunks, skipped_count = _pending_chunks(config, source, chunks, force)
        fetched_chunks = _fetch_chunks(config, source_key, source, pending_chunks, concurrency, fetcher)
        raw_count, filtered_count, stored_count = _write_chunks(config, source, fetched_chunks)
        status = "skipped" if skipped_count == len(chunks) else "succeeded"
        final_metadata = run_metadata | {
            "chunk_count": len(chunks),
            "skipped_count": skipped_count,
        }
        finish_run(
            config.database_path,
            run_id,
            status=status,
            raw_count=raw_count,
            stored_count=stored_count,
            filtered_count=filtered_count,
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


def _time_chunks(
    start_time: datetime,
    end_time: datetime,
    step: timedelta,
) -> list[tuple[datetime, datetime]]:
    chunks: list[tuple[datetime, datetime]] = []
    current = start_time
    while current < end_time:
        next_time = min(current + step, end_time)
        chunks.append((current, next_time))
        current = next_time
    return chunks


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


def _fetch_chunks(
    config: RadarConfig,
    source_key: str,
    source: MessageSource,
    chunks: list[tuple[datetime, datetime]],
    concurrency: int,
    fetcher: FetchMessages | None,
) -> list[tuple[datetime, datetime, list[RawMessage]]]:
    fetch_messages_fn = fetcher or _default_fetcher
    base_url = config.wechat_endpoint_url(source_key)
    max_workers = min(concurrency, len(chunks)) or 1

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                fetch_messages_fn,
                base_url,
                source,
                chunk_start,
                chunk_end,
                config.wechat.timeout,
            ): (chunk_start, chunk_end)
            for chunk_start, chunk_end in chunks
        }
        fetched = [
            (*futures[future], future.result())
            for future in as_completed(futures)
        ]
    return sorted(fetched, key=lambda item: item[0])


def _write_chunks(
    config: RadarConfig,
    source: MessageSource,
    chunks: list[tuple[datetime, datetime, list[RawMessage]]],
) -> tuple[int, int, int]:
    conn = connect(config.database_path)
    try:
        init_db(conn)
        raw_count = 0
        filtered_count = 0
        stored_count = 0
        for chunk_start, chunk_end, raw_messages in chunks:
            # 黑名单过滤在写库前完成，避免明显非投研群进入主表和 FTS。
            messages = [
                message
                for message in raw_messages
                if not is_group_blacklisted(message.group_name, config.filters.group_blacklist_patterns)
            ]
            raw_count += len(raw_messages)
            chunk_filtered_count = len(raw_messages) - len(messages)
            chunk_stored_count = upsert_messages(conn, messages)
            filtered_count += chunk_filtered_count
            stored_count += chunk_stored_count
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
        return raw_count, filtered_count, stored_count
    finally:
        conn.close()


def _run_target(source_key: str, start_time: datetime, end_time: datetime) -> str:
    return f"{source_key}:{start_time.isoformat()}..{end_time.isoformat()}"


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
